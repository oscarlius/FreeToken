"""D17's reviewable T16 case binding; it never substitutes cold probes for warm restore.

The historical full-tail runner has a closed case map and its ``run_arm`` only
owns cold probes.  This adapter preserves that runner's default environment and
cold argv, while describing the four R041 continuation cases for a separately
frozen continuation executor.  It fail-closes until the D14 T17 acceptance and
its independent review are supplied as sealed evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
CONTROL_COMMIT = "a9dca443cd07e1f60d1533e0a678935a09d21636"
CANDIDATE_COMMIT = "0aa23431e5b800797543bdecbf35a01045131d7d"
CONTROL_WORKTREE = Path("/data2/FreeToken/wt/e2d14-ordinary-rewind")
COLD_CONTROL_COMMIT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
COLD_CONTROL_WORKTREE = Path("/data2/FreeToken/wt/e2base")
CANDIDATE_WORKTREE = Path("/data2/FreeToken/wt/e2base1-ordinary-rewind")
ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
R041_CASES = (
    "prefix-8192-tail-65",
    "prefix-12416-tail-4097",
    "prefix-12736-tail-8193",
    "prefix-18944-tail-4097",
)
RID_RE = re.compile(r"E2-R041-gate-D17$")
SHA_RE = re.compile(r"[0-9a-f]{64}$")
COMBINED_T17_SCHEMA = "ft_t17_r036_r038_combined_28_review/v1"
# These external acceptance pins come from the completed, exit-0 D04 closure,
# not from fields supplied by the archive being checked.
COMBINED_T17_PINS = {
    "round_id": "E2-R038",
    "round_sha256": "97cfbb70fa470aec5567536fe6d727ca4790a337f4fce672b9f9484698949950",
    "review_sha256": "2e00291e3a70dfa63916fd323e97b14ae13f0a46c3d43fdd785a6501d3ec7716",
    "manifest_sha256": "65e23ebc09a675793fca70abb791385c41a8bf0be4b66411ed511c96f7f9d830",
}


class D17GateError(ValueError):
    pass


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_protocol():
    path = HERE / "t16_full_tail_base_runner.py"
    spec = importlib.util.spec_from_file_location("d17_t16_protocol", path)
    if spec is None or spec.loader is None:
        raise D17GateError("shared T16 full-tail protocol is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    helper_spec = importlib.util.spec_from_file_location('d17_case_owned_helpers', HERE / 'd17_frozen_helpers.py')
    if helper_spec is None or helper_spec.loader is None:
        raise D17GateError('owned helper verifier missing')
    helpers = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helpers)
    helpers.bind_protocol(module, HERE / 'helpers')
    return module


def d17_case() -> dict:
    """Return the exact D17 control/candidate binding without allocating a run."""
    return {
        "card": "D17",
        "control": {"worktree": str(CONTROL_WORKTREE), "commit": CONTROL_COMMIT},
        "candidate": {"worktree": str(CANDIDATE_WORKTREE), "commit": CANDIDATE_COMMIT},
        "cold": {"id_suffix": "cold", "target_tokens": 32052, "max_tokens": 128,
                 "control_worktree": str(COLD_CONTROL_WORKTREE), "control_commit": COLD_CONTROL_COMMIT},
        "continuation_cases": list(R041_CASES),
        "restore_roles": list(ROLES),
        "default_hooks": {"D06": False, "D07": False},
    }


def shared_default_environment(environ: dict[str, str] | None = None) -> dict[str, str]:
    """Use the reviewed T16 environment builder and retain its default-off rule."""
    protocol = _load_protocol()
    runner = object.__new__(protocol.Runner)
    runner.options = SimpleNamespace(gate="D17")
    previous = os.environ.copy()
    try:
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        env = runner.environment(CANDIDATE_WORKTREE)
    finally:
        if environ is not None:
            os.environ.clear()
            os.environ.update(previous)
    env["CUDA_VISIBLE_DEVICES"] = "0"
    return env


def shared_cold_argv(rid: str, arm: Path) -> list[str]:
    """Construct the unchanged T16 ``cold_eq.py`` argv, never a toy request."""
    if RID_RE.fullmatch(rid) is None:
        raise D17GateError("D17 requires the assigned E2-R041-gate-D17 RID")
    protocol = _load_protocol()
    cold = d17_case()["cold"]
    return [protocol.PY, str(protocol.SCR / "cold_eq.py"), rid + "-" + cold["id_suffix"],
            str(Path(arm) / "cold.json"), str(cold["target_tokens"]), str(cold["max_tokens"])]


def select_r041_cases(realinput28: Path | str) -> list[dict]:
    """Select exactly the PLAN §8.3 four cases from the existing real-input matrix."""
    selection_path = HERE / "t17_continuation_selection.py"
    spec = importlib.util.spec_from_file_location("d17_selection", selection_path)
    if spec is None or spec.loader is None:
        raise D17GateError("shared continuation selection is unavailable")
    selection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection)
    document = selection.load_realinput28(realinput28)
    rows = {row["name"]: row for row in selection._cases(document)}
    if set(R041_CASES) - set(rows):
        raise D17GateError("shared realinput28 lacks an R041 continuation case")
    return [{"name": name, "input_ids_sha256": rows[name]["input_ids_sha256"],
             "donor_input_ids_sha256": rows[name]["donor_input_ids_sha256"],
             "expected_tokens": 128, "compare": ["token_ids", "full_text", *ROLES]}
            for name in R041_CASES]


def _sealed_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise D17GateError("sealed read-only JSON evidence required")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise D17GateError("readable JSON evidence required") from error
    if not isinstance(value, dict):
        raise D17GateError("evidence object required")
    return value


def _recompute_closed_t17(directory: Path, closed: dict, review: dict) -> None:
    """Check D04 and preserve the independently accepted raw audit binding."""
    import importlib.util
    here = Path(__file__).resolve().parent
    def module(name, filename):
        spec = importlib.util.spec_from_file_location(name, here / filename)
        obj = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(obj)
        return obj
    retained = module('d17_d04_retained_check', 't17_continuation_runner.py')
    retained.d04_check(directory)
    if review.get('schema') == COMBINED_T17_SCHEMA:
        _verify_reused_t17(directory, closed, review)
        return
    auditor = module('d17_t17_raw_auditor', 't17_continuation_review.py')
    batch = review.get('batch')
    if type(batch) is not int or batch <= 0:
        raise D17GateError('actual T17 batch identity missing')
    recomputed = auditor.audit(directory, directory / 'launch_receipt.json',
                               directory / f'status_batch{batch}.json')
    if recomputed != review or closed.get('results') != recomputed:
        raise D17GateError('closed T17 audit differs from raw recomputation')
    expected = {f'prefix-{length}-tail-{tail}' for length in (8192,12416,12736,18944)
                for tail in (65,4095,4096,4097,8191,8192,8193)}
    rows = recomputed.get('cases', [])
    if len(rows) != 28 or {row.get('case') for row in rows} != expected:
        raise D17GateError('actual T17 audit lacks the exact 28 cases')
    if any(row.get('verdict') != 'measurements_pass_pending_independent_review' for row in rows):
        raise D17GateError('T17 contains a nonpassing case')


def _verify_reused_t17(directory: Path, closed: dict, review: dict) -> None:
    """Consume PLAN section 8.7's accepted 14+14 audit, without rerunning it."""
    expected = [f'prefix-{length}-tail-{tail}' for length in (8192,12416,12736,18944)
                for tail in (65,4095,4096,4097,8191,8192,8193)]
    coverage = review.get('canonical_coverage', {})
    retained = review.get('r036_retained_cases', [])
    measured = review.get('r038_recomputed_cases', [])
    if (closed.get('results') != review or len(retained) != 14 or len(measured) != 14
            or coverage.get('exact') is not True
            or coverage.get('actual_positions') != list(range(1,29))
            or coverage.get('actual_case_names') != expected
            or [row.get('position') for row in retained + measured] != list(range(1,29))):
        raise D17GateError('combined T17 lacks the exact ordered 14+14 coverage')

    def bound(path, digest):
        path = Path(path)
        if (any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file() or not isinstance(digest, str)
                or SHA_RE.fullmatch(digest) is None or _sha(path) != digest):
            raise D17GateError('combined T17 evidence binding differs: ' + str(path))
        return json.loads(path.read_text(encoding='utf-8'))

    permit = bound(directory/'retained_review.json', review.get('r036_reuse_license_sha256'))
    if (permit.get('schema') != 'ft_t17_retained_cases_review/v1'
            or permit.get('reuse_permitted') is not True
            or permit.get('source_rid') != 'E2-R036'
            or permit.get('target_candidate') != CONTROL_COMMIT
            or permit.get('computed_count') != 14):
        raise D17GateError('combined T17 retained-case permission differs')
    admitted = permit.get('admission_equivalence', {})
    if admitted.get('changed_python_files') != ['python/freetoken/scheduler/dev_prefill_schedule.py']:
        raise D17GateError('retained admission equivalence scope differs')
    bound(directory/'r037_closure_receipt.json', review.get('r037_closure_sha256'))
    bound(directory/'real_inputs.json', review.get('raw_input_sha256'))
    provenance = review.get('candidate_binding', {})
    bound(directory/'input_provenance.json', provenance.get('r038_input_provenance_sha256'))
    bound(directory/'result.json', review.get('r038_result_sha256'))
    permitted = {row['case']: row for row in permit.get('computed_cases', [])}
    if set(permitted) != set(expected[:14]):
        raise D17GateError('retained permission case coverage differs')
    for index, row in enumerate(retained + measured):
        case_path = Path(row['case_path'])
        name = expected[index]
        if case_path.name != name + '.json':
            raise D17GateError('combined T17 case order differs')
        source = Path(permit['source_round']) if index < 14 else directory
        if case_path != source/'cases'/(name+'.json'):
            raise D17GateError('combined T17 case origin differs')
        case = bound(case_path, row['case_sha256'])
        if (case['schedule'] != row['schedule_path']
                or case['evidence']['requested_input_ids_sha256'] != row['input_ids_sha256']):
            raise D17GateError('combined T17 case input/schedule differs')
        bound(row['schedule_path'], row['schedule_sha256'])
        if index < 14:
            item = permitted[name]
            if any(item[a] != row[b] for a,b in [('case_doc_sha256','case_sha256'),
                    ('input_ids_sha256','input_ids_sha256'),('schedule_sha256','schedule_sha256')]):
                raise D17GateError('retained case differs from independent permission')
        else:
            report = bound(directory/'independent_review'/case_path.name, row['report_sha256'])
            if (report.get('schema') != 'ft_r038_incremental_raw_recompute/v1'
                    or report.get('verdict') != 'PASS'
                    or report.get('case_sha256') != row['case_sha256']
                    or report.get('guard_installed') is not True
                    or report.get('cuda_visible_devices') != ''):
                raise D17GateError('incremental raw review differs')
            gate = report['case']['gate']
            if any(gate['state_handoff']['roles'].get(role) is not True for role in ROLES):
                raise D17GateError('incremental state comparison did not pass')
            for kind in ['repeat','warm_comparison']:
                comparison = gate['same_structure_reference'][kind]
                if (comparison.get('tokens_equal') is not True or comparison.get('text_equal') is not True
                        or comparison.get('first_token_fork') is not None):
                    raise D17GateError('incremental token/text comparison did not pass')


def verify_accepted_t17(closure: Path | str, independent_review: Path | str) -> dict:
    """Require a sealed accepted T17 closure and the matching independent review."""
    closure, independent_review = Path(closure), Path(independent_review)
    closed = _sealed_json(closure)
    review = _sealed_json(independent_review)
    directory = closure.parent
    if directory.is_symlink() or directory.stat().st_mode & 0o222:
        raise D17GateError('canonical T17 directory must be sealed')
    for item in directory.rglob('*'):
        if item.is_symlink() or item.stat().st_mode & 0o222:
            raise D17GateError('canonical T17 evidence tree must be sealed')
    if closure.name != 'round.json' or independent_review.parent != directory:
        raise D17GateError('canonical same-round evidence paths required')
    manifest = directory / "MANIFEST.sha256"
    if directory.is_symlink() or not directory.is_dir() or manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_mode & 0o222:
        raise D17GateError("canonical D04 T17 closure directory and manifest are required")
    declared = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as error:
            raise D17GateError("invalid canonical T17 manifest") from error
        relative = relative.removeprefix('./')
        if Path(relative).is_absolute() or '..' in Path(relative).parts or relative in declared:
            raise D17GateError('unsafe or duplicate canonical manifest path')
        path = directory / relative
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise D17GateError('canonical evidence contains a symlink')
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222 or _sha(path) != digest:
            raise D17GateError("canonical T17 manifest binding differs")
        declared[relative.removeprefix("./")] = digest
    # D04 deliberately pins mutable round.json through round_history/external
    # binding; it is not itself a MANIFEST member.  The independent audit is
    # archived evidence and must be manifest-bound.
    if independent_review.name not in declared:
        raise D17GateError("canonical T17 manifest omits independent review")
    experimental = closed.get("experimental", {})
    results = closed.get("results", {})
    if (closed.get("schema") != "ft_round/v2" or closed.get("card") != "T17"
            or closed.get("verdict") != "kept" or not closed.get("closed_at") or closed.get("retractions") != []
            or experimental.get("candidate_commit") != CONTROL_COMMIT
            or not isinstance(closed.get("round_id"), str)):
        raise D17GateError("accepted T17 closure for the exact D14 control is required")
    combined = review.get('schema') == COMBINED_T17_SCHEMA
    if combined:
        pins = COMBINED_T17_PINS
        if (closed['round_id'] != pins['round_id'] or directory.name != pins['round_id']
                or _sha(closure) != pins['round_sha256']
                or _sha(independent_review) != pins['review_sha256']
                or _sha(manifest) != pins['manifest_sha256']
                or review.get('candidate_commit') != CONTROL_COMMIT
                or review.get('verdict') != 'PASS_ALL_28_PENDING_CANONICAL_D04'):
            raise D17GateError('combined T17 external acceptance pins differ')
    elif (not isinstance(results, dict) or results.get("schema") != "ft_t17_continuation_independent_audit/v1"
            or results.get("candidate_commit") != CONTROL_COMMIT or len(results.get("cases", [])) != 28
            or results.get("verdict") != "kept_pending_independent_review"):
        raise D17GateError("canonical T17 all-28 independent raw audit is required")
    if not combined and (review.get("schema") != "ft_t17_continuation_independent_audit/v1"
            or review.get("verdict") != "kept_pending_independent_review"
            or review.get("candidate_commit") != CONTROL_COMMIT):
        raise D17GateError("independent all-28 audit for the exact D14 control is required")
    expected = closed.get("independent_review_sha256")
    if not isinstance(expected, str) or SHA_RE.fullmatch(expected) is None or expected != _sha(independent_review):
        raise D17GateError("T17 closure does not bind the independent review bytes")
    if not combined and review.get("rid") != closed["round_id"]:
        raise D17GateError("independent review RID differs from accepted T17 closure")
    _recompute_closed_t17(directory, closed, review)
    return {"closure": str(closure), "closure_sha256": _sha(closure),
            "review": str(independent_review), "review_sha256": _sha(independent_review),
            "rid": closed["round_id"], "control_commit": CONTROL_COMMIT}


def verify_worktree(path: Path | str, commit: str) -> dict:
    root = Path(path)
    if root.is_symlink():
        raise D17GateError("D17 worktree cannot be a symlink")
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != commit or dirty:
        raise D17GateError("D17 worktree commit or tracked-clean state differs")
    return {"worktree": str(root.resolve()), "commit": commit, "tracked_clean": True}


def verify_no_foreign_gpu_lock(lock: Path | str) -> str:
    """A D17 executor must see an absent global lock before it can allocate GPU."""
    path = Path(lock)
    if path.exists() or path.is_symlink():
        raise D17GateError("foreign GPU lock exists")
    return str(path)


def preflight(*, rid: str, realinput28: Path | str, accepted_t17: Path | str,
              independent_review: Path | str, control_worktree: Path | str = CONTROL_WORKTREE,
              candidate_worktree: Path | str = CANDIDATE_WORKTREE,
              cold_control_worktree: Path | str = COLD_CONTROL_WORKTREE,
              gpu_lock: Path | str = "/data2/_shared/gpu.lock") -> dict:
    if RID_RE.fullmatch(rid) is None:
        raise D17GateError("D17 requires the assigned E2-R041-gate-D17 RID")
    return {"schema": "ft_d17_t16_case/v1", "admitted": False, "requests_sent": False,
            "rid": rid, "case": d17_case(), "control": verify_worktree(control_worktree, CONTROL_COMMIT),
            "candidate": verify_worktree(candidate_worktree, CANDIDATE_COMMIT),
            "cold_control": verify_worktree(cold_control_worktree, COLD_CONTROL_COMMIT),
            "accepted_t17": verify_accepted_t17(accepted_t17, independent_review),
            "gpu_lock_absent": verify_no_foreign_gpu_lock(gpu_lock),
            "cold_argv": shared_cold_argv(rid, Path("R041_CANDIDATE")),
            "continuations": select_r041_cases(realinput28),
            "stop_condition": "execute only through a separately frozen shared T16/continuation runner"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rid", required=True); parser.add_argument("--realinput28", required=True)
    parser.add_argument("--accepted-t17", required=True); parser.add_argument("--independent-review", required=True)
    parser.add_argument("--control-worktree", default=str(CONTROL_WORKTREE))
    parser.add_argument("--candidate-worktree", default=str(CANDIDATE_WORKTREE))
    parser.add_argument("--cold-control-worktree", default=str(COLD_CONTROL_WORKTREE))
    parser.add_argument("--gpu-lock", default="/data2/_shared/gpu.lock")
    args = parser.parse_args(argv)
    print(json.dumps(preflight(rid=args.rid, realinput28=args.realinput28, accepted_t17=args.accepted_t17,
                               independent_review=args.independent_review, control_worktree=args.control_worktree,
                               candidate_worktree=args.candidate_worktree,
                               cold_control_worktree=args.cold_control_worktree,
                               gpu_lock=args.gpu_lock), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
