"""Review-gated, single-writer launcher for T16 D14."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
PY = str(ROOT / "venv/bin/python")
LAUNCH_BASE_SHA256 = "7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf"
PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
NEW = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"


def _load_base(stage: Path):
    path = stage / "t16_candidate_launch_full_tail.py"
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != LAUNCH_BASE_SHA256:
        raise ValueError("reviewed 7e1c05a launcher is missing or changed")
    spec = importlib.util.spec_from_file_location("ft_t16_d14_launch_base", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def _read_stage(stage: Path) -> tuple[dict, dict]:
    report_path = stage / "cpu_validation.json"
    report = json.loads(report_path.read_text())
    required = {"t16_d14_runner.py", "t16_d14_cpu_stage.py", "t16_d14_launch.py",
                "t16_candidate_runner_full_tail.py", "t16_full_tail_base_runner.py",
                "t16_candidate_launch_full_tail.py",
                "t16_legacy_base_runner.py", "tests/test_t16_shared_prefill.py",
                "tests/test_t16_full_tail.py", "tests/test_t16_candidate_runner_full_tail.py",
                "tests/fixtures/t16_failed_full_tail.json",
                "tests/engine/test_layer_major_tracks.py"}
    if report.get("schema") != "ft_t16_d14_cpu_stage/v1" or report.get("gpu_started") is not False:
        raise ValueError("D14 CPU staging receipt is not a CPU-only proof")
    if set(report.get("files", {})) != required or len(report.get("steps", [])) != 2:
        raise ValueError("D14 CPU staging receipt is incomplete")
    for name, digest in report["files"].items():
        path = stage / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"D14 staged source changed: {name}")
    if [(step.get("commit"), step.get("returncode"), step.get("expected_returncode"))
            for step in report["steps"]] != [(PARENT, 1, 1), (NEW, 0, 0)]:
        raise ValueError("D14 CPU before/after proof does not bind the expected outcomes")
    if [step.get("pytest") for step in report["steps"]] != [
        {"count": 13, "outcome": "failed"}, {"count": 13, "outcome": "passed"}
    ]:
        raise ValueError("D14 CPU receipt does not distinguish 13 failures from import failure")
    for step in report["steps"]:
        log = Path(step.get("output_path", ""))
        if (not log.is_file() or log.is_symlink()
                or hashlib.sha256(log.read_bytes()).hexdigest() != step.get("output_sha256")
                or step.get("binding", {}).get("head") != step.get("commit")):
            raise ValueError("D14 CPU logs or isolated source bindings changed")
    harness = report.get("harness_regression", {})
    harness_log = Path(harness.get("output_path", ""))
    if (harness.get("passed") != 39 or harness.get("returncode") != 0
            or not harness_log.is_file() or harness_log.is_symlink()
            or hashlib.sha256(harness_log.read_bytes()).hexdigest() != harness.get("output_sha256")):
        raise ValueError("shared T16 harness has no fresh Linux regression proof")
    replay = report.get("r020_read_only_replay", {})
    raw = stage / "r020_raw_replay.json"
    if (not raw.is_file() or raw.is_symlink()
            or hashlib.sha256(raw.read_bytes()).hexdigest() != replay.get("raw_replay_sha256")
            or replay.get("replay", {}).get("prefill", {}).get("all_prefill_events") != 13):
        raise ValueError("D14 has no fresh read-only R020 13-row replay")
    return report, replay


def _freeze(stage: Path, report: dict) -> Path:
    parent = Path("/tmp")
    mode = parent.stat().st_mode
    if parent.is_symlink() or not stat.S_ISDIR(mode) or mode & 0o022 and not mode & stat.S_ISVTX:
        raise ValueError("unsafe D14 execution-copy parent")
    execution = Path(tempfile.mkdtemp(prefix="ft-t16-d14-", dir=parent))
    try:
        for name, digest in report["files"].items():
            source, target = stage / name, execution / name
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"staged source changed before freeze: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o444)
        for directory in sorted((path for path in execution.rglob("*") if path.is_dir()), reverse=True):
            directory.chmod(0o555)
        execution.chmod(0o555)
        return execution
    except BaseException:
        for path in sorted(execution.rglob("*"), reverse=True):
            if path.is_file():
                path.chmod(0o600)
                path.unlink()
            else:
                path.rmdir()
        execution.rmdir()
        raise


def preflight(stage: Path) -> tuple[object, dict, list[str], str, int, Path]:
    if sys.platform != "linux":
        raise ValueError("D14 launch requires the Linux test host")
    base = _load_base(stage)
    report, _ = _read_stage(stage)
    current = Path(__file__)
    staged_launcher = stage / "t16_d14_launch.py"
    if (current.is_symlink() or current.resolve() != staged_launcher.resolve()
            or hashlib.sha256(current.read_bytes()).hexdigest() != report["files"].get(staged_launcher.name)):
        raise ValueError("D14 launcher must execute from its frozen staged source")
    runner = stage / "t16_d14_runner.py"
    runner_sha = report["files"][runner.name]
    base_runner = stage / "t16_full_tail_base_runner.py"
    module = base.verified_module(runner, runner_sha, "ft_t16_d14_runner")
    if module.D14["parent_commit"] != PARENT or module.D14["new_commit"] != NEW:
        raise ValueError("D14 runner binding differs from launcher binding")
    helper = base.verified_module(ROOT / "runs/plan_batches/e2_launch.py", base.HELPER_SHA, "ft_d14_atomic_helper")
    number, batch = base.next_round(ROUNDS), helper.next_batch(ROUNDS)
    rid = f"E2-R{number:03d}-gate-D14"
    argv = [PY, "-u", str(runner), "--case", "D14", "--rid", rid, "--batch", str(batch),
            "--candidate-commit", NEW]
    subprocess.run(argv, check=True, timeout=120)
    if base.next_round(ROUNDS) != number or helper.next_batch(ROUNDS) != batch or (ROUNDS / rid).exists():
        raise ValueError("round ledger changed during D14 preflight")
    return base, report, argv, rid, batch, base_runner


def launch(stage: Path) -> None:
    base, report, argv, rid, batch, base_runner = preflight(stage)
    helper = base.verified_module(ROOT / "runs/plan_batches/e2_launch.py", base.HELPER_SHA, "ft_d14_helper")
    execution = _freeze(stage, report)
    argv[2] = str(execution / "t16_d14_runner.py")
    receipt_path = ROOT / "runs/dev_D14" / f"launch_{rid}.json"
    reserved = {"schema": "ft_t16_d14_launch/v1", "state": "reserved", "rid": rid, "batch": batch,
                "card": "D14", "parent_commit": PARENT, "candidate_commit": NEW,
                "source_stage": str(stage), "runner_sha256": report["files"]["t16_d14_runner.py"],
                "frozen_runner": argv[2],
                "base_runner_sha256": report["files"]["t16_full_tail_base_runner.py"],
                "cpu_stage_sha256": hashlib.sha256((stage / "cpu_validation.json").read_bytes()).hexdigest(),
                "launcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    print(json.dumps(base.reserve_process(helper, batch, rid, argv, receipt_path, reserved)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--launch", action="store_true")
    options = parser.parse_args()
    if options.launch:
        launch(options.stage)
    else:
        base, report, argv, rid, batch, _ = preflight(options.stage)
        print(json.dumps({"state": "preflight_only", "rid": rid, "batch": batch, "argv": argv,
                          "cpu_stage_files": report["files"]}), flush=True)
