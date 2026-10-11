"""Fail-closed initial D04 closure for the actual T20 E2-R040 batch 71.

This module is intentionally inert unless ``--close`` is supplied on Linux.
It never creates an admission record and it never changes an open/live round.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re


ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
RID = "E2-R040"
BATCH = 71
CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"
CODE_VERSION = "E2-base.1@0aa23431"
GENERIC = ROOT / "runs/plan_batches/initial_measurement_close.py"
GENERIC_SHA256 = "dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835"
RECEIPT = ROOT / "runs/dev_D17/launch_E2-R040_batch71.json"
BATCH_SCRIPT = ROOT / "runs/plan_batches/batch71_E2-R040_python.sh"
ARMS = ("PRODUCTION", "OFF_p1", "ON_p1", "OFF_p2", "ON_p2", "OFF_p3", "ON_p3")
ARM_FILES = ("source.json", "compiled_extensions.json", "SERVE_CMD.txt", "serve.log",
             "performance_measurements.json", "tax.json")
CONTROL_NAMES = ("round.json", "round_history", "MANIFEST.sha256")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def load_generic(path: Path = GENERIC):
    """Load only the reviewed immutable generic publisher."""
    if not path.is_file() or sha256(path) != GENERIC_SHA256:
        raise ValueError("initial close generic source pin differs")
    spec = importlib.util.spec_from_file_location("t20_initial_close_generic", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load initial close generic")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _positive_int(value, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"positive {label} required")
    return value


def _same_identity(value: dict, *, label: str) -> None:
    if (value.get("rid") != RID or value.get("batch") != BATCH
            or value.get("candidate_commit") != CANDIDATE):
        raise ValueError(f"{label} identity differs from actual T20")


def _validate_arm(directory: Path, arm: str) -> None:
    arm_dir = directory / arm
    if not arm_dir.is_dir():
        raise ValueError(f"required T20 arm missing: {arm}")
    for name in ARM_FILES:
        path = arm_dir / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"required {arm} evidence missing: {name}")
    source = read_json(arm_dir / "source.json")
    if source.get("commit") != CANDIDATE or source.get("code_version") != CODE_VERSION:
        raise ValueError(f"{arm} source identity differs")


def _validate_prerequisite(directory: Path) -> dict:
    prerequisite = read_json(directory / "prerequisite.json")
    if (prerequisite.get("round") != "E2-R041-gate-D17"
            or prerequisite.get("batch") != 68
            or prerequisite.get("candidate_commit") != CANDIDATE):
        raise ValueError("R041 prerequisite binding differs")
    for key in ("round_sha256", "manifest_sha256", "closure_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(prerequisite.get(key))) is None:
            raise ValueError(f"R041 prerequisite lacks {key}")
    return prerequisite


def _validate_review(path: Path) -> dict:
    review = read_json(path)
    _same_identity(review, label="independent review")
    if review.get("verdict") != "PASS":
        raise ValueError("independent PASS review required")
    return review


def validate(directory: Path, review_path: Path, receipt_path: Path, generic, *, batch_script: Path = BATCH_SCRIPT) -> dict:
    """Validate terminal evidence without fabricating an admission document."""
    if not directory.is_dir():
        raise ValueError("R040 round directory missing")
    if any((directory / item).exists() for item in CONTROL_NAMES):
        raise ValueError("initial closure only; existing control artifact refused")
    if (directory / "admission.json").exists():
        raise ValueError("R040 uses launch receipt; unexpected admission refused")
    generic.assert_owned_tree(directory)
    if review_path.parent != directory:
        raise ValueError("independent review must belong to R040")
    review = _validate_review(review_path)
    status = read_json(directory / f"status_batch{BATCH}.json")
    if status.get("rid") != RID or status.get("batch") != BATCH or status.get("card") != "T20":
        raise ValueError("status identity differs from actual T20")
    batch_pid = _positive_int(status.get("batch_pid"), "batch_pid")
    if status.get("state") != "complete_measurements_pending_independent_review":
        raise ValueError("T20 measurements are not terminal pending independent review")
    receipt = read_json(receipt_path)
    _same_identity(receipt, label="launch receipt")
    if receipt.get("schema") != "ft_t20_actual_launch/v1":
        raise ValueError("unexpected launch receipt schema")
    if _positive_int(receipt.get("batch_pid"), "receipt batch_pid") != batch_pid:
        raise ValueError("status and receipt batch PID differ")
    ticks = _positive_int(receipt.get("batch_start_ticks"), "receipt batch_start_ticks")
    if generic.live_or_zombie(batch_pid):
        raise ValueError("T20 controller remains live")
    service_pid = status.get("service_pid")
    if service_pid is not None and generic.live_or_zombie(_positive_int(service_pid, "service_pid")):
        raise ValueError("T20 owned service remains live")
    lock = Path("/data2/_shared/gpu.lock")
    if lock.exists():
        raise ValueError("R040 GPU lock remains live")
    prerequisite = _validate_prerequisite(directory)
    archive_path = directory / "execution_archive.json"
    archive = read_json(archive_path)
    files = archive.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("execution archive lacks source_tools file hashes")
    for name in ("t20_measurements.py", "t17_continuation_runner_v2.py"):
        value = files.get(name)
        if re.fullmatch(r"[0-9a-f]{64}", value if isinstance(value, str) else "") is None:
            raise ValueError(f"execution archive lacks pinned source tool: {name}")
    if re.fullmatch(r"[0-9a-f]{64}", str(archive.get("cpu_report_sha256"))) is None:
        raise ValueError("execution archive lacks CPU source-package hash")
    for arm in ARMS:
        _validate_arm(directory, arm)
    log = directory.parent / f"batch{BATCH}.log"
    argv = receipt.get("argv")
    if not isinstance(argv, list) or not any(str(item).endswith("t17_continuation_runner_v2.py") for item in argv):
        raise ValueError("launch receipt lacks actual T20 runner argv")
    if not batch_script.is_file() or not batch_script.stat().st_size or not log.is_file() or not log.stat().st_size:
        raise ValueError("actual batch script and log are required")
    return {
        "schema": "ft_round/v2", "round_id": RID, "epoch": 2, "card": "T20",
        "verdict": "pending_review", "proposed_verdict": None,
        "verdict_history": [], "retractions": [],
        "created_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST"),
        "closed_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST"),
        "base": {"commit": CANDIDATE, "code_version": CODE_VERSION},
        "binding": {"batch": BATCH, "batch_pid": batch_pid, "batch_start_ticks": ticks,
                    "launch_receipt_sha256": sha256(receipt_path),
                    "independent_review_sha256": sha256(review_path),
                    "r041_prerequisite": prerequisite},
        "execution_archive": {"path": str(archive_path), "sha256": sha256(archive_path),
                              "cpu_report_sha256": archive["cpu_report_sha256"]}, "arms": list(ARMS),
        "batch_logs": [{"path": str(log), "sha256": sha256(log)},
                       {"path": str(batch_script), "sha256": sha256(batch_script)}], "manifest": "MANIFEST.sha256",
    }


def close(directory: Path, review_path: Path, receipt_path: Path = RECEIPT, *, generic=None) -> dict:
    if platform.system() != "Linux" or directory != ROUNDS / RID:
        raise ValueError("actual close requires Linux canonical E2-R040 round root")
    generic = generic or load_generic()
    document = validate(directory, review_path, receipt_path, generic)
    generic.publish(directory, generic.build_control(directory, document))
    return document


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--review", type=Path)
    options = parser.parse_args(argv)
    if not options.close:
        print(json.dumps({"rid": RID, "batch": BATCH, "state": "close_prepared", "closed": False}))
        return 0
    if options.review is None:
        raise ValueError("--close requires the independent review path")
    close(ROUNDS / RID, options.review)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
