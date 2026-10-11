"""Fail-closed, atomically owned launcher for a newly assigned T17 continuation run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
PY = str(ROOT / "venv/bin/python")
GPU_LOCK = Path("/data2/_shared/gpu.lock")
CANDIDATE = "a9dca443cd07e1f60d1533e0a678935a09d21636"
PARENT = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
PRIOR_RID, PRIOR_BATCH = "E2-R037-gate-D14", 66
INPUT_SHA256 = "90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0"
RID_RE = re.compile(r"E2-R0(?:3[5-9])$")
LAUNCHER_REVIEW_SCHEMA = "ft_t17_v3_launcher_review/v1"


class LaunchError(ValueError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise LaunchError("sealed read-only regular file required: " + str(path))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise LaunchError("module is unavailable: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict:
    frozen(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LaunchError("JSON object required")
    return value


def source_root(stage: Path) -> Path:
    root = stage / "source_tools"
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o222:
        raise LaunchError("sealed source_tools archive required")
    return root


def load_admission(stage: Path):
    root = source_root(stage)
    report = stage / "startup_cpu_report.json"
    document = _json(report)
    digest = document.get("files", {}).get("t17_source_admission.py")
    path = root / "t17_source_admission.py"
    frozen(path)
    if not isinstance(digest, str) or sha(path) != digest:
        raise LaunchError("source admission bytes are not bound by startup report")
    return load_module("t17_v3_source_admission", path), report, document


def verify_source_startup(stage: Path, review: Path, review_sha256: str) -> dict:
    admission, report, document = load_admission(stage)
    checked = admission.verify(report, review, review_sha256)
    expected = {"source_execution_ready": True, "runtime_lifecycle_verified": False,
                "model_admitted": False, "candidate_commit": CANDIDATE, "parent_commit": PARENT}
    if any(checked.get(key) is not value if isinstance(value, bool) else checked.get(key) != value for key, value in expected.items()):
        raise LaunchError("independent source-startup review cannot admit runtime/model")
    if document.get("candidate_commit") != CANDIDATE or document.get("parent_commit") != PARENT:
        raise LaunchError("startup report candidate binding differs")
    return {**checked, "files": document["files"], "startup_report": str(report), "startup_report_sha256": sha(report),
            "legacy_cpu_validation_sha256": sha(source_root(stage) / "cpu_validation.json")}


def verify_launcher_review(template: Path, review: Path, review_sha256: str) -> dict:
    frozen(Path(__file__))
    frozen(template)
    if not isinstance(review_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", review_sha256) is None:
        raise LaunchError("caller-pinned launcher review SHA required")
    review = Path(review)
    if review.resolve().is_relative_to(HERE.resolve()):
        raise LaunchError("launcher review must be external")
    frozen(review)
    if sha(review) != review_sha256:
        raise LaunchError("launcher review SHA differs")
    value = _json(review)
    required = {"schema": LAUNCHER_REVIEW_SCHEMA, "verdict": "PASS",
                "launcher_sha256": sha(Path(__file__)), "batch_template_sha256": sha(template),
                "gpu_started": False, "requests_sent": False}
    if any(value.get(key) is not expected if isinstance(expected, bool) else value.get(key) != expected for key, expected in required.items()):
        raise LaunchError("launcher/template CPU review binding differs")
    return {"launcher_review_sha256": review_sha256, "launcher_sha256": required["launcher_sha256"],
            "batch_template_sha256": required["batch_template_sha256"]}


def _protocol(root: Path):
    path = root / "t17_owned_launch_protocol.py"
    frozen(path)
    return load_module("t17_v3_owned_protocol", path)


def _runtime(root: Path):
    path = root / "t17_continuation_runtime_v2.py"
    frozen(path)
    return load_module("t17_v3_runtime", path)


def _selection(root: Path):
    path = root / "t17_continuation_selection.py"
    frozen(path)
    return load_module("t17_v3_selection", path)


def _runner(root: Path) -> Path:
    path = root / "t17_continuation_runner_v2.py"
    frozen(path)
    return path


def _realinput(inputs: Path, selection) -> None:
    frozen(inputs)
    if sha(inputs) != INPUT_SHA256:
        raise LaunchError("realinput28 raw SHA differs")
    document = selection.load_realinput28(inputs, expected_document_sha256=INPUT_SHA256)
    if len(document.get("cases", [])) != 28:
        raise LaunchError("formal T17 requires all 28 real inputs")


def _case_args(cases, resume_review, resume_review_sha256):
    if cases == "all" and resume_review is None and resume_review_sha256 is None:
        return ["--cases", "all"]
    if cases != "remaining" or resume_review is None or not isinstance(resume_review_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", resume_review_sha256) is None:
        raise LaunchError("remaining cases require an explicit pinned resume review")
    frozen(Path(resume_review))
    if sha(Path(resume_review)) != resume_review_sha256:
        raise LaunchError("resume review SHA differs")
    return ["--cases", "remaining", "--resume-review", str(resume_review),
            "--resume-review-sha256", resume_review_sha256]


def _resource_preflight(runner: Path, root: Path, *, rid: str, batch: int, inputs: Path, closure: Path, rounds: Path,
                        cases="all", resume_review=None, resume_review_sha256=None) -> list[str]:
    if GPU_LOCK.exists():
        raise LaunchError("foreign GPU lock is present")
    argv = [PY, "-u", str(runner), "--realinput28", str(inputs), "--candidate-worktree", str(ROOT / "wt/e2d14-ordinary-rewind"),
            "--candidate-sha", CANDIDATE, "--parent-sha", PARENT, "--run-kind", "t17",
            "--envelope-cases", "sample4", "--rid", rid, "--batch", str(batch)]
    argv += _case_args(cases, resume_review, resume_review_sha256)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    subprocess.run(argv, check=True, timeout=180, env=env, cwd=root)
    if GPU_LOCK.exists():
        raise LaunchError("resource preflight changed GPU lock")
    return argv


def _identity(process) -> dict:
    pid = getattr(process, "pid", None)
    if type(pid) is not int or pid <= 0:
        raise LaunchError("atomic launch returned invalid PID")
    stat_path = Path("/proc") / str(pid) / "stat"
    fields = stat_path.read_text().rpartition(") ")[2].split()
    ticks = int(fields[19])
    if ticks <= 0 or os.getpgid(pid) != pid:
        raise LaunchError("owned process identity differs")
    return {"batch_pid": pid, "batch_pgid": pid, "batch_start_ticks": ticks, "batch_execution_id": f"{pid}:{ticks}"}


class _OwnedPid:
    def __init__(self, pid: int): self.pid = pid
    def poll(self):
        try: os.kill(self.pid, 0)
        except ProcessLookupError: return 0
        return None


def build_command(template: Path, *, stage: Path, root: Path, rid: str, batch: int, inputs: Path, closure: Path,
                  review: Path, review_sha256: str, receipt: Path, rounds: Path,
                  cases="all", resume_review=None, resume_review_sha256=None) -> list[str]:
    _case_args(cases, resume_review, resume_review_sha256)
    command = ["env", "FT_T17_STAGE=" + str(stage), "FT_T17_SOURCE_ROOT=" + str(root), "FT_T17_BATCH=" + str(batch),
            "FT_T17_BATCH_TEMPLATE=" + str(template),
            "FT_T17_INPUTS=" + str(inputs), "FT_T17_CLOSURE_BINDING=" + str(closure),
            "FT_T17_SOURCE_REVIEW=" + str(review), "FT_T17_SOURCE_REVIEW_SHA256=" + review_sha256,
            "FT_T17_PREFLIGHT_ARTIFACT=" + str(receipt.with_name(receipt.stem + ".preflight.json")),
            "FT_T17_ROUNDS=" + str(rounds), "FT_T17_CANDIDATE_WORKTREE=" + str(ROOT / "wt/e2d14-ordinary-rewind"),
            "FT_T17_CASES=" + cases]
    if cases == "remaining":
        command += ["FT_T17_RESUME_REVIEW=" + str(resume_review), "FT_T17_RESUME_REVIEW_SHA256=" + resume_review_sha256]
    return command + ["bash", str(template), rid]


def preflight(stage: Path, source_review: Path, source_review_sha256: str, *, launcher_review: Path,
              launcher_review_sha256: str, rid: str, inputs: Path, closure: Path, template: Path,
              rounds: Path = ROUNDS, receipt_root: Path = ROOT / "runs/dev_D16", protocol=None, atomic=None,
              cases="all", resume_review=None, resume_review_sha256=None) -> dict:
    stage = Path(stage); inputs = Path(inputs); closure = Path(closure); template = Path(template); rounds = Path(rounds)
    if RID_RE.fullmatch(rid) is None:
        raise LaunchError("only M-assigned E2-R035 through E2-R039 are allowed")
    startup = verify_source_startup(stage, Path(source_review), source_review_sha256)
    own = verify_launcher_review(template, Path(launcher_review), launcher_review_sha256)
    root = source_root(stage); runtime = _runtime(root); selection = _selection(root); runner = _runner(root)
    _realinput(inputs, selection)
    frozen(closure)
    candidate = runtime.verify_candidate(ROOT / "wt/e2d14-ordinary-rewind", CANDIDATE, PARENT)
    prior = runtime.verify_t16(rounds, closure, rid=PRIOR_RID, batch=PRIOR_BATCH, parent=PARENT, candidate=CANDIDATE)
    protocol = protocol or _protocol(root)
    atomic = atomic or protocol.verified_module(ROOT / "runs/plan_batches/e2_launch.py", protocol.HELPER_SHA, "t17_v3_atomic")
    number, batch = protocol.next_round(rounds), atomic.next_batch(rounds)
    if number != int(rid[-3:]) or (rounds / rid).exists() or (rounds / rid).is_symlink():
        raise LaunchError("round ledger does not reserve requested RID")
    receipt = Path(receipt_root) / ("launch_" + rid + ".json")
    # ``e2_launch.reserve_and_launch`` owns logs directly under the round ledger.
    batch_log = rounds / ("batch" + str(batch) + ".log")
    if receipt.resolve().is_relative_to(stage.resolve()):
        raise LaunchError("preflight artifact must be outside the sealed source package")
    if receipt.exists() or receipt.is_symlink() or batch_log.exists() or GPU_LOCK.exists():
        raise LaunchError("receipt, batch log, or foreign GPU lock already exists")
    dry_argv = _resource_preflight(runner, root, rid=rid, batch=batch, inputs=inputs, closure=closure, rounds=rounds,
                                 cases=cases, resume_review=resume_review, resume_review_sha256=resume_review_sha256)
    if protocol.next_round(rounds) != number or atomic.next_batch(rounds) != batch or (rounds / rid).exists() or receipt.exists() or batch_log.exists() or GPU_LOCK.exists():
        raise LaunchError("round/batch/resource ledger changed during preflight")
    command = build_command(template, stage=stage, root=root, rid=rid, batch=batch, inputs=inputs, closure=closure,
                            review=Path(source_review), review_sha256=source_review_sha256, receipt=receipt, rounds=rounds,
                            cases=cases, resume_review=resume_review, resume_review_sha256=resume_review_sha256)
    return {"schema": "ft_t17_continuation_launch_v3_preflight/v1", "rid": rid, "batch": batch,
            "stage": str(stage), "source_root": str(root), "rounds": str(rounds), "receipt": str(receipt),
            "case_mode": cases, "resume_review": str(resume_review) if resume_review is not None else None,
            "resume_review_sha256": resume_review_sha256,
            "batch_log": str(batch_log), "expected_round_number": number, "command": command,
            "resource_preflight_argv": dry_argv, "resource_preflight_cuda_visible_devices": "", "candidate": candidate, "prior_t16": prior,
            "startup": startup, "launcher": own, "runner_sha256": sha(runner),
            "runner_files": startup["files"] if "files" in startup else None,
            "inputs_sha256": sha(inputs), "closure_sha256": sha(closure), "admitted": False,
            "model_admitted": False, "runtime_lifecycle_verified": False}


def launch(preflight_result: dict, *, protocol, atomic) -> dict:
    receipt = Path(preflight_result["receipt"])
    rounds = Path(preflight_result["rounds"])
    rid, batch = preflight_result["rid"], preflight_result["batch"]
    _case_args(preflight_result.get("case_mode", "all"), preflight_result.get("resume_review"),
               preflight_result.get("resume_review_sha256"))
    source_files = preflight_result.get("runner_files")
    if not isinstance(source_files, dict) or "t17_continuation_runner.py" not in source_files:
        raise LaunchError("auditable legacy runner source inventory is required")
    if (receipt.exists() or GPU_LOCK.exists() or (rounds / rid).exists()
            or Path(preflight_result["batch_log"]).exists()
            or protocol.next_round(rounds) != preflight_result["expected_round_number"]
            or atomic.next_batch(rounds) != batch):
        raise LaunchError("launch identity or GPU resource changed after preflight")
    reserved = {"schema": "ft_t17_continuation_launch_v3/v1", "state": "reserved", "rid": rid, "batch": batch,
                "candidate_commit": CANDIDATE, "parent_commit": PARENT, "stage": preflight_result["stage"], "source_stage": preflight_result["stage"],
                "source_root": preflight_result["source_root"], "startup_report_sha256": preflight_result["startup"]["startup_report_sha256"],
                "independent_source_review_sha256": preflight_result["startup"]["independent_review_sha256"],
                "legacy_cpu_validation_sha256": preflight_result["startup"]["legacy_cpu_validation_sha256"],
                "stage_report_sha256": preflight_result["startup"]["legacy_cpu_validation_sha256"],
                "launcher_review_sha256": preflight_result["launcher"]["launcher_review_sha256"],
                "launcher_sha256": preflight_result["launcher"]["launcher_sha256"],
                "batch_template_sha256": preflight_result["launcher"]["batch_template_sha256"],
                "runner_sha256": preflight_result["runner_sha256"], "runner_source_inventory": source_files,
                "source_files": source_files,
                "inputs_sha256": preflight_result["inputs_sha256"], "closure_sha256": preflight_result["closure_sha256"],
                "case_mode": preflight_result.get("case_mode", "all"),
                "resume_review": preflight_result.get("resume_review"),
                "resume_review_sha256": preflight_result.get("resume_review_sha256"),
                "model_admitted": False, "runtime_lifecycle_verified": False}
    receipt_value = protocol.reserve_process(atomic, batch, rid, preflight_result["command"], receipt, reserved)
    process = _OwnedPid(receipt_value["batch_pid"])
    identity = {}
    try:
        identity = _identity(process)
        current = receipt.stat()
        protocol.publish_receipt(receipt, (current.st_dev, current.st_ino), {**receipt_value, **identity})
    except BaseException as publication_error:
        cleanup_error = None
        try: protocol.stop_owned_process(process)
        except BaseException as error: cleanup_error = repr(error)
        recovery = {**receipt_value, **identity, "state": "cleanup_failure" if cleanup_error else "identity_publish_failed_stopped",
                    "receipt_error": repr(publication_error), "cleanup_error": cleanup_error}
        try: protocol.write_exclusive(receipt.with_name(receipt.name + ".identity_cleanup.json"), recovery)
        except BaseException as sidecar_error: recovery["sidecar_error"] = repr(sidecar_error)
        raise LaunchError("birth identity receipt publication failed") from publication_error
    return {**receipt_value, **identity}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True); parser.add_argument("--source-review", type=Path, required=True)
    parser.add_argument("--source-review-sha256", required=True); parser.add_argument("--launcher-review", type=Path, required=True)
    parser.add_argument("--launcher-review-sha256", required=True); parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--rid", required=True); parser.add_argument("--inputs", type=Path, required=True); parser.add_argument("--closure", type=Path, required=True)
    parser.add_argument("--cases", choices=("all", "remaining"), default="all")
    parser.add_argument("--resume-review", type=Path); parser.add_argument("--resume-review-sha256")
    parser.add_argument("--launch", action="store_true"); args = parser.parse_args(argv)
    result = preflight(args.stage, args.source_review, args.source_review_sha256, launcher_review=args.launcher_review,
                       launcher_review_sha256=args.launcher_review_sha256, rid=args.rid, inputs=args.inputs,
                       closure=args.closure, template=args.template, cases=args.cases,
                       resume_review=args.resume_review, resume_review_sha256=args.resume_review_sha256)
    if not args.launch:
        print(json.dumps(result, sort_keys=True)); return 0
    protocol = _protocol(Path(result["source_root"]))
    atomic = protocol.verified_module(ROOT / "runs/plan_batches/e2_launch.py", protocol.HELPER_SHA, "t17_v3_atomic_launch")
    print(json.dumps(launch(result, protocol=protocol, atomic=atomic), sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
