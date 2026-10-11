"""Verify a sealed CPU source/startup package without admitting a T17 GPU run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = "/data2/FreeToken/venv/bin/python"
CANDIDATE = "a9dca443cd07e1f60d1533e0a678935a09d21636"
PARENT = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
WORKTREE = Path("/data2/FreeToken/wt/e2d14-ordinary-rewind")
# Reuse the existing historical CPU input archive; never clone it for a launch.
RETAINED_FIXTURE_ROOT = Path("/data2/FreeToken/runs/dev_D16/v2_retained_cpu_f0f3a1abd0fc")
RETAINED_FIXTURE_CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
RETAINED_REPLAY_REPORT_SHA = "ee4f8dbc5ff2feebdb98a393f0aca9277ddf299fcac35b796e8e6ddf560ab247"
SCENARIOS = ("success", "request_error", "stop_error")
TEST_MODULES = (
    "tests/test_t17_continuation_selection.py",
    "tests/test_t17_continuation_runner_v2.py",
    "tests/test_t17_operator_observe.py",
    "tests/test_t17_source_admission.py",
    "tests/test_t17_continuation_launch_v3.py",
    "tests/scripts/test_equiv_suite.py",
    "tests/scripts/test_equiv_continuation.py",
    "tests/scripts/test_equiv_path_readers.py",
    "tests/scripts/test_equiv_retained_d03.py",
    "tests/scripts/test_equiv_sampler_capture.py",
    "tests/scripts/test_equiv_retained_state.py",
    "tests/scripts/test_equiv_service_capture.py",
)
SUITE_FILES = (
    "__init__.py", "__main__.py", "cases.py", "continuation.py", "gate.py",
    "historical.py", "path_readers.py", "raw.py", "retained_d03.py",
    "retained_state.py", "sampler_capture.py", "schedule.py",
    "service_capture.py", "service_capture_startup.py",
)
HELPERS = ("cold_eq.py", "probe_ft_cold32k.py", "ft_probe_ckpt_tax.py", "serve_args_diff.py")
IMPORT_CODE = (
    "import pathlib,torch,freetoken,t17_continuation_runtime_v2,sitecustomize,socket; "
    "assert sitecustomize.FT_CPU_FIXTURE_NETWORK_GUARD is True; "
    "assert socket.socket.connect is sitecustomize.connect; "
    "assert socket.socket.connect_ex is sitecustomize.connect_ex; "
    "p=pathlib.Path(freetoken.__file__).resolve(); "
    "assert p.is_relative_to(pathlib.Path('/data2/FreeToken/wt/e2d14-ordinary-rewind/python')); "
    "assert not torch.cuda.is_initialized(); print(p)"
)
IMPORT_ARGV = (PY, "-c", IMPORT_CODE)
CPU_SCHEMA = "ft_t17_gpu_source_cpu/v1"
ADMISSION_SCHEMA = "ft_t17_gpu_source_admission/v1"
REVIEW_SCHEMA = "ft_t17_gpu_source_admission_review/v1"
T20_SOURCE_FILES = (
    "t20_measurements.py", "e2_runtime.py", "t00_runner.py", "t08_runner.py", "t16_runner.py", "d07_g3g4_prepare.py",
    "d16_native_process_collection.py", "d16_service_workloads.py", "d16_exact_service_startup.py",
    "equiv_suite/native_workloads.py", "batchNN_E2-R040.sh", "batchNN_E2-R040_continuation_v3.sh",
    "t20_r041_sample4_closure.py", "d17_gate_case.py", "serve_args_diff.py", "round_json_append.py",
)


def for_run(run_kind: str):
    """Return an isolated verifier with fixed identities for the selected run.

    Report contents never choose the candidate or worktree. T20 consumes the
    cold R041 prerequisite against E2-base, independently of its warm control.
    """
    if run_kind not in ("t17", "t20"):
        raise AdmissionError("unknown source-startup run kind")
    owned = _module("ft_owned_source_admission_" + run_kind, HERE / "t17_source_admission.py")
    if run_kind == "t20":
        owned.CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"
        owned.PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
        owned.WORKTREE = Path("/data2/FreeToken/wt/e2base1-ordinary-rewind")
        owned.IMPORT_CODE = IMPORT_CODE.replace(WORKTREE.as_posix(), owned.WORKTREE.as_posix())
        owned.IMPORT_CODE = owned.IMPORT_CODE.replace(
            "import pathlib,torch,", "import pathlib,torch,t20_measurements,e2_runtime,t08_runner,").replace(
            "assert not torch.cuda.is_initialized();", "source=pathlib.Path(t17_continuation_runtime_v2.__file__).resolve().parent; assert all(pathlib.Path(x.__file__).resolve().parent == source for x in (t20_measurements,e2_runtime,t08_runner)); assert socket.socket.listen is sitecustomize.listen; assert not torch.cuda.is_initialized();")
        owned.IMPORT_ARGV = (PY, "-c", owned.IMPORT_CODE)
        owned.CPU_SCHEMA = "ft_t20_gpu_source_cpu/v1"
        owned.ADMISSION_SCHEMA = "ft_t20_gpu_source_admission/v1"
        owned.REVIEW_SCHEMA = "ft_t20_gpu_source_admission_review/v1"
        owned.TEST_MODULES = TEST_MODULES + (
            "tests/test_t20_r041_sample4_closure.py", "tests/test_t17_runtime_r041_recheck.py",
            "tests/test_d16_service_workloads.py", "tests/test_d16_native_process_collection.py",
        )
    return owned


class AdmissionError(ValueError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matches(value: dict, expected: dict) -> bool:
    """Keep boolean gate flags typed while comparing immutable strings by value."""
    return all(value.get(key) is target if isinstance(target, bool) else value.get(key) == target
               for key, target in expected.items())


def sealed_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o222:
        raise AdmissionError("sealed evidence directory required")
    if any(path.is_symlink() or path.stat().st_mode & 0o222 for path in root.rglob("*")):
        raise AdmissionError("evidence tree is not sealed")


def file(root: Path, name: str) -> Path:
    if (not isinstance(name, str) or name.startswith(("/", "\\")) or Path(name).is_absolute()
            or ".." in Path(name).parts):
        raise AdmissionError("unsafe evidence path")
    path = root / name
    if (any(item.is_symlink() for item in (path, *path.parents)) or not path.is_file()
            or path.stat().st_mode & 0o222 or not path.resolve().is_relative_to(root.resolve())):
        raise AdmissionError("sealed regular evidence path required")
    return path


def _sealed_json(root: Path, name: str) -> tuple[Path, bytes, dict]:
    path = file(root, name)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdmissionError("sealed JSON object required") from exc
    if not isinstance(value, dict):
        raise AdmissionError("sealed JSON object required")
    return path, raw, value


def verify_map(root: Path, values: dict) -> None:
    if not isinstance(values, dict) or not values:
        raise AdmissionError("nonempty evidence inventory required")
    for name, digest in values.items():
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise AdmissionError("invalid evidence SHA")
        if sha(file(root, name)) != digest:
            raise AdmissionError("evidence SHA differs: " + name)


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AdmissionError("runtime source is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cpu_flags(report: dict) -> None:
    expected = {
        "runtime_lifecycle_verified": False, "model_admitted": False, "admitted": False,
        "gpu_started": False, "requests_sent": False, "fixture_only": True,
        "real_gpu_lock_unchanged": True, "cpu_lifecycle_contract_verified": True,
    }
    if report.get("schema") != CPU_SCHEMA or report.get("verdict") != "PASS":
        raise AdmissionError("CPU source report schema/verdict differs")
    if not _matches(report, expected):
        raise AdmissionError("CPU source contract cannot substitute model acceptance")


def _git_tree() -> None:
    if WORKTREE.is_symlink():
        raise AdmissionError("regular candidate worktree required")
    head = subprocess.check_output(["git", "-C", str(WORKTREE), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(WORKTREE), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    if head != CANDIDATE or dirty:
        raise AdmissionError("candidate worktree differs")


def _required_sources(runtime) -> set[str]:
    return (set(runtime.REQUIRED_SOURCE_FILES) | set(runtime.GENERATED_SOURCE_FILES)
            | {"t17_source_admission.py", "t17_v2_retained_replay.py", "d17_frozen_helpers.py",
               "cpu_validation.json", "t17_continuation_launch_v3.py", "batchNN_T17_v3.sh",
               "tests/test_t17_source_admission.py", *TEST_MODULES}
            | {"equiv_suite/" + name for name in SUITE_FILES}
            | {prefix + name for prefix in ("helpers/", "helpers/raw/") for name in HELPERS})


def _verify_pytest(report: dict, root: Path) -> None:
    expected = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", *TEST_MODULES]
    log = file(root.parent, report.get("log_path"))
    if (report.get("argv") != expected or report.get("pytest_returncode") != 0
            or sha(log) != report.get("log_sha256")):
        raise AdmissionError("CPU test invocation/log differs")
    text = log.read_text(encoding="utf-8", errors="replace")
    counts = re.findall(r"(\d+) passed", text)
    if (len(counts) != 1 or report.get("passed") != int(counts[0])
            or re.search(r"\b(?:failed|skipped|error)\b", text, re.IGNORECASE)):
        raise AdmissionError("complete CPU tests did not pass")


def _verify_import(report: dict, root: Path) -> None:
    if report.get("import_argv") != list(IMPORT_ARGV) or report.get("import_returncode") != 0:
        raise AdmissionError("actual candidate import invocation differs")
    log = file(root, "import.log")
    if sha(log) != report.get("import_log_sha256") or log.read_text().strip() != str(WORKTREE / "python/freetoken/__init__.py"):
        raise AdmissionError("actual candidate import differs")


def _identity(value: dict) -> tuple[int, str]:
    pid, ticks = value.get("pid"), value.get("start_ticks")
    if type(pid) is not int or type(ticks) is not int or min(pid, ticks) <= 0:
        raise AdmissionError("typed CPU child birth differs")
    execution_id = f"{pid}:{ticks}"
    if value.get("execution_id") != execution_id:
        raise AdmissionError("CPU child birth binding differs")
    return pid, execution_id


def _verify_stop_evidence(name: str, calls: list[dict]) -> None:
    services = [item for item in calls if item.get("kind") == "cpu_service"]
    if not services or any(not isinstance(item.get("identity"), dict) for item in services):
        raise AdmissionError("CPU child birth set differs")
    births = [_identity(item["identity"]) for item in services]
    born_pids = [pid for pid, _ in births]
    if len(born_pids) != len(set(born_pids)) or len({execution_id for _, execution_id in births}) != len(births):
        raise AdmissionError("CPU child birth set differs")
    stops = [item for item in calls if item.get("kind") == "cpu_stop"]
    stop_pids = []
    for item in stops:
        pid = item.get("pid")
        if type(pid) is not int or pid <= 0 or item.get("group_dead") is not True:
            raise AdmissionError("owned CPU child stop evidence differs")
        stop_pids.append(pid)
    if len(stop_pids) != len(born_pids) or set(stop_pids) != set(born_pids) or len(stop_pids) != len(set(stop_pids)):
        raise AdmissionError("owned CPU child stop set differs")
    if name == "stop_error":
        failed = [item.get("pid") for item in calls if item.get("kind") == "stop_failed"]
        if not failed or any(type(pid) is not int or pid <= 0 or pid not in born_pids for pid in failed):
            raise AdmissionError("stop-error failure evidence differs")
        if any(item.get("recovered_after_stop_error") is not True for item in stops):
            raise AdmissionError("stop-error recovery evidence differs")
    elif any("recovered_after_stop_error" in item for item in stops):
        raise AdmissionError("ordinary replay cannot claim stop-error recovery")
    if name == "success" and len(born_pids) != 4:
        raise AdmissionError("successful retained replay lifecycle differs")


def _verify_steps(report: dict, stage: Path, root: Path) -> None:
    steps = report.get("steps")
    if not isinstance(steps, dict) or set(steps) != set(SCENARIOS):
        raise AdmissionError("three lifecycle scenarios required")
    for name in SCENARIOS:
        row = steps[name]
        log = file(stage, name + ".log")
        receipt_path, _, receipt = _sealed_json(stage, name + "_replay.json")
        expected_argv = [PY, str(root / "t17_v2_retained_replay.py"), "--stage", str(stage), "--scenario", name]
        if row.get("argv") != expected_argv or row.get("returncode") != 0 or sha(log) != row.get("log_sha256"):
            raise AdmissionError("lifecycle step/log differs: " + name)
        expected = {"scenario": name, "fixture_only": True, "admitted": False,
                    "gpu_started": False, "requests_sent": False,
                    "source_model_round": "E2-R034a", "original_model_generation": False,
                    "verdict": "PASS"}
        if not _matches(receipt, expected) or not isinstance(receipt.get("calls"), list):
            raise AdmissionError("CPU replay receipt scope differs")
        _verify_stop_evidence(name, receipt["calls"])


def _verify_snapshot(stage: Path) -> None:
    retained = RETAINED_FIXTURE_ROOT
    sealed_tree(retained)
    if sha(file(retained, "cpu_replay_report.json")) != RETAINED_REPLAY_REPORT_SHA:
        raise AdmissionError("retained fixture receipt SHA differs")
    _, _, manifest = _sealed_json(retained, "fixture_manifest.json")
    if (manifest.get("fixture_only") is not True or manifest.get("admitted") is not False
            or manifest.get("source_model_round") != "E2-R034a" or manifest.get("source_candidate") != RETAINED_FIXTURE_CANDIDATE):
        raise AdmissionError("fixture manifest scope differs")
    values = manifest.get("snapshot_files")
    if not isinstance(values, dict) or not values:
        raise AdmissionError("fixture snapshot inventory required")
    snapshot = retained / "snapshot"
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise AdmissionError("regular fixture snapshot required")
    actual = {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()}
    if actual != set(values):
        raise AdmissionError("fixture snapshot inventory is incomplete")
    for name, entry in values.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            raise AdmissionError("fixture snapshot provenance differs")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None or sha(file(snapshot, name)) != digest:
            raise AdmissionError("fixture snapshot SHA differs")


def _verify_helpers(root: Path) -> None:
    protocol = _module("t17_source_admission_protocol", root / "t16_full_tail_base_runner.py")
    helpers = _module("t17_source_admission_helpers", root / "d17_frozen_helpers.py")
    try:
        helpers.bind_protocol(protocol, root / "helpers")
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        raise AdmissionError("frozen T16 helper archive differs") from exc


def check_cpu_package(report_path: Path | str) -> dict:
    report_path = Path(report_path)
    root = HERE
    stage = root.parent
    if report_path.resolve() != (stage / "startup_cpu_report.json").resolve():
        raise AdmissionError("executor must use its own startup CPU report")
    sealed_tree(stage)
    _, raw, report = _sealed_json(stage, "startup_cpu_report.json")
    _cpu_flags(report)
    if report.get("candidate_commit") != CANDIDATE or report.get("parent_commit") != PARENT or report.get("candidate_worktree") != str(WORKTREE):
        raise AdmissionError("CPU candidate/parent binding differs")
    files, outputs = report.get("files"), report.get("output_files")
    verify_map(root, files)
    verify_map(stage, outputs)
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != set(files):
        raise AdmissionError("CPU source map is not complete")
    actual_outputs = {path.relative_to(stage).as_posix() for path in stage.rglob("*") if path.is_file() and not path.is_relative_to(root) and path.name != "startup_cpu_report.json"}
    if actual_outputs != set(outputs):
        raise AdmissionError("CPU output map is not complete")
    runtime = _module("t17_source_admission_runtime", root / "t17_continuation_runtime_v2.py")
    if not _required_sources(runtime) <= set(files):
        raise AdmissionError("CPU required source inventory incomplete")
    if CPU_SCHEMA == "ft_t20_gpu_source_cpu/v1" and not set(T20_SOURCE_FILES) <= set(files):
        raise AdmissionError("T20 measurement source inventory incomplete")
    _verify_pytest(report, root)
    _verify_import(report, root)
    _verify_steps(report, stage, root)
    _verify_snapshot(stage)
    _verify_helpers(root)
    _git_tree()
    return {"schema": ADMISSION_SCHEMA, "stage_report_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_commit": CANDIDATE, "parent_commit": PARENT,
            "source_execution_ready": False, "model_admitted": False, "runtime_lifecycle_verified": False}


def verify(report_path: Path | str, review_path: Path | str | None = None, expected_review_sha256: str | None = None) -> dict:
    checked = check_cpu_package(report_path)
    if review_path is None:
        return checked
    review_path = Path(review_path)
    if review_path.resolve().is_relative_to(HERE.parent.resolve()):
        raise AdmissionError("independent review must be external to immutable CPU package")
    if not isinstance(expected_review_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_review_sha256) is None:
        raise AdmissionError("caller-pinned independent review SHA required")
    sealed_tree(review_path.parent)
    review_file, raw, review = _sealed_json(review_path.parent, review_path.name)
    if hashlib.sha256(raw).hexdigest() != expected_review_sha256:
        raise AdmissionError("independent review SHA differs")
    required = {"schema": REVIEW_SCHEMA, "scope": "owned-gpu-test-startup-only",
                "verdict": "PASS", "stage_report_sha256": checked["stage_report_sha256"],
                "candidate_commit": CANDIDATE, "parent_commit": PARENT,
                "runtime_lifecycle_verified": False, "model_admitted": False, "admitted": False,
                "gpu_started": False, "requests_sent": False, "reviewer_identity": "/root/r_overlap_review"}
    if not _matches(review, required):
        raise AdmissionError("independent CPU source-startup review binding differs")
    return {**checked, "source_execution_ready": True, "independent_review_sha256": expected_review_sha256,
            "scope": "owned-gpu-test-startup-only"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--review-sha256")
    parser.add_argument("--run-kind", choices=("t17", "t20"), default="t17")
    args = parser.parse_args()
    print(json.dumps(for_run(args.run_kind).verify(args.report, args.review, args.review_sha256), sort_keys=True))
