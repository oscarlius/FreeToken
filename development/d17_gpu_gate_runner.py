"""Actual (but separately admitted) D17 R041 executor built on retained T16/T17 services.

This is deliberately an adapter, not a synthetic cold-loop.  The common T16
``Runner.run_arm`` performs the cold comparison; each R041 row then starts one
real D14-control and one real D17-candidate warm service through
``t17_d14_gpu.Run.service``/``request``.  The resulting verdict can only be
``measurements_pass_pending_independent_review``.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import argparse
import re
import subprocess

HERE = Path(__file__).resolve().parent
_case_spec = importlib.util.spec_from_file_location("d17_gate_case", HERE / "d17_gate_case.py")
if _case_spec is None or _case_spec.loader is None:
    raise RuntimeError("D17 case adapter is unavailable")
case_gate = importlib.util.module_from_spec(_case_spec)
sys.modules[_case_spec.name] = case_gate
_case_spec.loader.exec_module(case_gate)
CONTROL = case_gate.CONTROL_COMMIT
CANDIDATE = case_gate.CANDIDATE_COMMIT
COLD_CONTROL = case_gate.COLD_CONTROL_COMMIT
ROLES = case_gate.ROLES


class D17ExecutionError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise D17ExecutionError("retained module is unavailable: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def execution_cases(document):
    selection = _load('d17_execution_case_selection', HERE / 't17_continuation_selection.py')
    rows = {row['name']: row for row in selection._cases(document)}
    result = []
    for name in case_gate.R041_CASES:
        case = dict(rows[name])
        context = case['query'][case['length'] - 2:case['length']]
        if len(context) != 2 or any(type(value) is not int for value in context):
            raise D17ExecutionError('byte-bound boundary context missing: '+name)
        for field in ('context', 'expected_ngram'):
            if field in case and case[field] != context:
                raise D17ExecutionError('declared boundary context differs from actual query: '+name)
        case['context'] = context
        result.append(case)
    return result


def retained_modules():
    """Load retained lifecycle/readers once; callers inject mocks in CPU tests."""
    sys.path.insert(0, str(HERE))
    gpu = _load("d17_retained_gpu", HERE / "t17_d14_gpu.py")
    artifacts = _load("d17_retained_artifacts", HERE / "t17_d14_artifacts.py")
    helpers = _load('d17_owned_helpers', HERE / 'd17_frozen_helpers.py')
    helpers.bind_protocol(gpu.protocol, HERE / 'helpers')
    # The retained loader supplies the package context required by raw.py's
    # relative schedule import; loading raw.py as a naked file would not.
    continuation_runner = _load("d17_retained_continuation", HERE / "t17_continuation_runner.py")
    _, _, continuation = continuation_runner._suite_modules()
    return gpu, artifacts, continuation.raw


@contextlib.contextmanager
def rebound(gpu, worktree: Path, commit: str):
    """Temporarily bind a fresh retained Run instance to one exact source tree."""
    old_wt, old_candidate = gpu.WT, gpu.helper.CANDIDATE
    try:
        gpu.WT, gpu.helper.CANDIDATE = Path(worktree), commit
        yield
    finally:
        gpu.WT, gpu.helper.CANDIDATE = old_wt, old_candidate


def _identity(base) -> dict:
    pid = getattr(getattr(base, "proc", None), "pid", None)
    if type(pid) is not int or pid <= 0:
        raise D17ExecutionError("live service PID required")
    stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8").rpartition(") ")[2].split()
    ticks = int(stat[19])
    if ticks <= 0:
        raise D17ExecutionError("service birth ticks required")
    return {"pid": pid, "start_ticks": ticks, "execution_id": f"{pid}:{ticks}"}


def _state_bytes(artifacts, root: Path, role_record: dict):
    filename = role_record.get("resume", {}).get("file")
    expected = role_record.get("resume", {}).get("sha256")
    if not isinstance(filename, str) or Path(filename).is_absolute() or ".." in Path(filename).parts:
        raise D17ExecutionError("restore role file binding missing: " + str(filename))
    raw = root / filename
    path = raw.resolve(strict=True)
    if raw.is_symlink() or root.resolve() not in path.parents or not path.is_file() or not isinstance(expected, str) or _sha(path) != expected:
        raise D17ExecutionError("restore role path/SHA binding differs")
    tensor = artifacts.load_tensor(path)
    return path, tensor


def compare_warm(artifacts, left: dict, right: dict) -> dict:
    """Compare real warm responses and restore tensors between D14 and D17."""
    if (len(left["warm"]["token_ids"]) != 128 or len(right["warm"]["token_ids"]) != 128
            or left["warm"].get("input_ids_sha256") != right["warm"].get("input_ids_sha256")
            or left.get("coordinate") != right.get("coordinate")
            or left["process_identity"] == right["process_identity"]):
        raise D17ExecutionError("warm 128-token/input/coordinate/independent-process binding differs")
    output = {"token_ids_equal": left["warm"]["token_ids"] == right["warm"]["token_ids"],
              "full_text_equal": left["warm"]["text"] == right["warm"]["text"], "roles": {}}
    for role in ROLES:
        lp, lt = _state_bytes(artifacts, Path(left["arm"]) / "dump", left["restore_roles"][role])
        rp, rt = _state_bytes(artifacts, Path(right["arm"]) / "dump", right["restore_roles"][role])
        output["roles"][role] = {"bitwise_equal": bool(artifacts.bit_equal(lt, rt)),
                                 "left_sha256": _sha(lp), "right_sha256": _sha(rp)}
    output["passed"] = output["token_ids_equal"] and output["full_text_equal"] and all(
        row["bitwise_equal"] for row in output["roles"].values())
    return output


def warm_service(*, gpu, artifacts, raw, base, worktree: Path, commit: str, label: str, case: dict) -> dict:
    """Execute donor2+hit128 through the retained service/request interface."""
    with rebound(gpu, worktree, commit):
        def operation(arm):
            identity = _identity(base)
            # Persist the actual live server birth before sending either request.
            # Later R041 readers can bind raw receipts to this same service.
            with (arm / "owned_process.json").open("x", encoding="utf-8") as stream:
                json.dump(identity, stream, sort_keys=True)
            base.request(arm, "donor", case["donor"], 0, 2)
            base.request(arm, "hit", case["query"], case["length"], 128)
            if _identity(base) != identity:
                raise D17ExecutionError("warm service birth identity changed during requests")
            result = raw.read_warm(artifacts, arm, case, query="hit")
            result.update(arm=str(arm), process_identity=identity, candidate_commit=commit,
                          coordinate=case["length"],
                          argv_sha256=_sha(arm / "SERVE_CMD.txt"),
                          compiled_sha256=_sha(arm / "compiled_extensions.json"),
                          environment_sha256=_sha(arm / "environment.json"))
            return result
        return base.service(label, operation, health_only=True)


def common_cold_compare(owner, gpu, control_wt: Path, candidate_wt: Path):
    """Compare two default cold arms with the retained T16 checks.

    Default arms do not generate D0 prefill telemetry. Runner.compare requires
    that telemetry, so use its default-path checks directly instead.
    """
    with rebound(gpu, control_wt, COLD_CONTROL):
        parent = owner.run_arm("CONTROL_COLD_DEFAULT", control_wt, COLD_CONTROL, False,
                               layer_major=True)
    with rebound(gpu, candidate_wt, CANDIDATE):
        target = owner.run_arm("CANDIDATE_COLD_DEFAULT", candidate_wt, CANDIDATE, False,
                               layer_major=True)
    checks = gpu.protocol
    args = checks['strict_args'](owner.parser(str(parent / 'serve.log')),
                                 owner.parser(str(target / 'serve.log')), owner.allowed)
    try:
        cold = checks['check_det']([parent / 'det.json', target / 'det.json'], 32052, 128)
    except ValueError as error:
        if str(error) != 'TEXT DIFF':
            raise
        return {'schema': 'ft_d17_default_cold/v1', 'passed': False,
                'reason': 'TEXT DIFF', 'control': str(parent), 'candidate': str(target),
                'control_commit': COLD_CONTROL, 'candidate_commit': CANDIDATE}
    a, b = (parent / 'prefill_seq.txt').read_bytes(), (target / 'prefill_seq.txt').read_bytes()
    if not a or a != b:
        raise D17ExecutionError('default cold business prefill sequence differs')
    return {'schema': 'ft_d17_default_cold/v1', 'passed': True, 'args': args,
            'cold': cold, 'sequence': 'SAME', 'layer_major': True,
            'control': str(parent), 'candidate': str(target),
            'control_commit': COLD_CONTROL, 'candidate_commit': CANDIDATE}


def _make_owner(gpu, options):
    class GateRun(gpu.Run):
        def set_status(self, **values):
            return gpu.protocol['Runner'].set_status(self, rid=self.options.rid,
                                                    card='T16', **values)
        def service(self, name, operation, **kwargs):
            # Origins differ between candidate worktrees. Compare imported binary
            # bytes across worktrees while preserving each arm's actual paths.
            extensions = self.compiled_extensions(gpu.WT)
            if not isinstance(extensions, dict) or set(extensions) != {'_cpu_moe', '_pinned_tensor'}:
                raise D17ExecutionError('actual compiled extension inventory differs')
            hashes = {key: record['sha256'] for key, record in extensions.items()}
            if any(not isinstance(value, str) or len(value) != 64 for value in hashes.values()):
                raise D17ExecutionError('compiled extension SHA binding missing')
            previous = getattr(self, '_cross_worktree_extension_sha', None)
            if previous is not None and previous != hashes:
                raise D17ExecutionError('compiled extension binary changed across worktrees')
            self._cross_worktree_extension_sha = hashes
            self.extensions = extensions
            return super().service(name, operation, **kwargs)
        def lock_take(self):
            # R041 is D17's formal T16 gate; the retained generic lock is T16.
            return gpu.protocol['Runner'].lock_take(self)
    return GateRun(options)


def execute(options, *, protocol, gpu, artifacts, raw, cases: list[dict]) -> dict:
    """Run one cold common-T16 pair plus eight real warm services, retaining cleanup."""
    if not getattr(options, "run", False):
        return {"gpu_started": False, "admitted": False, "reason": "--run required"}
    if len(cases) != 4 or [row["name"] for row in cases] != list(case_gate.R041_CASES):
        raise D17ExecutionError("exact four R041 cases required")
    owner = _make_owner(gpu, options)
    owner.directory = Path(options.directory)
    owner.status = owner.directory / f"status_batch{options.batch}.json"
    if Path(options.directory).exists():
        raise FileExistsError("R041 evidence directory already exists")
    owner.lock_take(); lock_owned = True; created = False
    try:
        owner.directory.mkdir(); created = True
        owner.set_status(state="running")
        options.lock_token, options.lock_inode = owner.token, owner.lock_inode
        result = {"schema": "ft_d17_r041/v1", "rid": options.rid, "candidate_commit": CANDIDATE,
                  "control_commit": CONTROL, "admitted": False, "cold": common_cold_compare(
                      owner, gpu, Path(getattr(options, 'cold_control_worktree', case_gate.COLD_CONTROL_WORKTREE)),
                      Path(options.candidate_worktree)), "cases": {}}
        if result['cold'].get('passed') is False:
            result['verdict'] = 'not_met'
            with (owner.directory / 'result.json').open('x') as stream:
                json.dump(result, stream, sort_keys=True)
            owner.set_status(state='complete_measurements_not_met', verdict='not_met')
            return result
        for case in cases:
            left = warm_service(gpu=gpu, artifacts=artifacts, raw=raw, base=owner,
                                worktree=Path(options.control_worktree), commit=CONTROL,
                                label=case["name"] + "-d14-warm", case=case)
            right = warm_service(gpu=gpu, artifacts=artifacts, raw=raw, base=owner,
                                 worktree=Path(options.candidate_worktree), commit=CANDIDATE,
                                 label=case["name"] + "-d17-warm", case=case)
            compared = compare_warm(artifacts, left, right)
            result["cases"][case["name"]] = {"control": left, "candidate": right, "comparison": compared}
            if not compared["passed"]:
                result["verdict"] = "not_met"
                (owner.directory / "result.json").write_text(json.dumps(result, sort_keys=True) + "\n")
                owner.set_status(state="complete_measurements_not_met", verdict="not_met")
                return result
        result["verdict"] = "measurements_pass_pending_independent_review"
        result_path = owner.directory / 'result.json'
        with result_path.open('x') as stream:
            json.dump(result, stream, sort_keys=True)
        # Publish the ordinary T16 gate shape after every R041 measurement.
        # Independent review and canonical D04 acceptance remain separate.
        with (owner.directory / f'gate_batch{options.batch}.json').open('x') as stream:
            json.dump({'gate': 'T16', 'candidate_case': 'D17', 'rid': options.rid,
                       'batch': options.batch, 'parent_commit': COLD_CONTROL,
                       'new_commit': CANDIDATE, 'warm_control_commit': CONTROL,
                       'proposed_verdict': 'kept', 'admitted': False,
                       'result_sha256': _sha(result_path)}, stream, sort_keys=True)
        owner.set_status(state="complete_measurements_pending_review", verdict=result["verdict"])
        return result
    except BaseException as error:
        if created:
            with (owner.directory / 'failed_harness.json').open('x') as stream:
                json.dump({'schema': 'ft_d17_r041_failed_harness/v1', 'rid': options.rid,
                           'candidate_commit': CANDIDATE, 'error': repr(error),
                           'admitted': False}, stream, sort_keys=True)
            owner.set_status(state="failed", error=repr(error))
        raise
    finally:
        try:
            owner.stop()
        finally:
            if lock_owned and owner.proc is None:
                owner.lock_release()


def _sealed(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise D17ExecutionError("sealed CPU admission evidence required")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise D17ExecutionError("CPU admission evidence object required")
    return value


def verify_execution_admission(stage: Path, review: Path, review_sha256=None) -> dict:
    """Validate script readiness without promoting CPU evidence to model truth."""
    admission = _load('d17_cpu_source_admission', HERE / 'd17_source_admission.py')
    report = Path(stage) / 'source_tools' / 'cpu_validation.json'
    return admission.verify(report, review, review_sha256)


def verify_candidate_tag(tag: str, worktree: Path, commit: str) -> str:
    match = re.fullmatch(r"E2-base\.1@([0-9a-f]{7,40})", tag or "")
    if match is None or match.group(1) != commit[:len(match.group(1))]:
        raise D17ExecutionError("exact E2-base.1 candidate tag required before R041")
    actual = subprocess.check_output(
        ["git", "-C", str(worktree), "rev-parse", "refs/tags/" + tag + "^{commit}"], text=True).strip()
    if actual != commit:
        raise D17ExecutionError("E2-base.1 tag points to another candidate")
    return tag


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rid", required=True); parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True); parser.add_argument("--realinput28", type=Path, required=True)
    parser.add_argument("--accepted-t17", type=Path, required=True); parser.add_argument("--independent-review", type=Path, required=True)
    parser.add_argument("--source-cpu-stage", type=Path); parser.add_argument("--source-review", type=Path); parser.add_argument("--source-review-sha256")
    parser.add_argument("--control-worktree", type=Path, default=case_gate.CONTROL_WORKTREE)
    parser.add_argument("--candidate-worktree", type=Path, default=case_gate.CANDIDATE_WORKTREE)
    parser.add_argument("--cold-control-worktree", type=Path, default=case_gate.COLD_CONTROL_WORKTREE)
    parser.add_argument("--candidate-tag")
    parser.add_argument("--run", action="store_true"); args = parser.parse_args(argv)
    args.gate = "D17"
    case_gate.preflight(rid=args.rid, realinput28=args.realinput28, accepted_t17=args.accepted_t17,
                        independent_review=args.independent_review, control_worktree=args.control_worktree,
                        candidate_worktree=args.candidate_worktree, cold_control_worktree=args.cold_control_worktree)
    if not args.run:
        print(json.dumps({"gpu_started": False, "admitted": False, "reason": "--run required"}, sort_keys=True)); return 0
    if args.source_cpu_stage is None or args.source_review is None:
        raise D17ExecutionError("--run requires frozen CPU lifecycle stage and independent review")
    verify_candidate_tag(args.candidate_tag, args.candidate_worktree, CANDIDATE)
    verify_execution_admission(args.source_cpu_stage, args.source_review, args.source_review_sha256)
    selector = _load("d17_execution_selection", HERE / "t17_continuation_selection.py")
    document = selector.load_realinput28(args.realinput28)
    cases = execution_cases(document)
    protocol = _load("d17_common_t16", HERE / "t16_full_tail_base_runner.py")
    gpu, artifacts, raw = retained_modules()
    if args.directory != gpu.ROUNDS / args.rid:
        raise D17ExecutionError("output directory must be the assigned canonical rounds path")
    result = execute(args, protocol=protocol, gpu=gpu, artifacts=artifacts, raw=raw, cases=cases)
    print(json.dumps(result, sort_keys=True)); return 0 if result["verdict"] == "measurements_pass_pending_independent_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
