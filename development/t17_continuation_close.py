"""Fail-closed D04 closure for one measured T17 continuation round.

The closer has no authority to classify a round.  It archives only the exact
result produced by the frozen independent auditor, after that result has been
recomputed from the round's raw evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
LAUNCH_RECEIPTS = ROOT / "runs/dev_D16"
LOCK = Path("/data2/_shared/gpu.lock")
PARENT = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
TOOLS = {
    "round_json_append.py": "67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff",
    "round_close.py": "fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5",
    "round_close.sh": "6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9",
}
STAGE_SCHEMA = "ft_t17_continuation_close_cpu/v1"
STAGE_FILES = {
    "t17_continuation_close.py",
    "t17_continuation_review.py",
    "tests/test_t17_continuation_close.py",
    "tests/test_t17_continuation_review.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def xwrite(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def regular_readonly(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("read-only regular evidence required: " + str(path))


def regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular evidence file required: " + str(path))


def load(path: Path) -> dict:
    regular(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required: " + str(path))
    return value


def no_symlinks(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir() or any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("symlink evidence path")


def terminal(identity: dict) -> None:
    pid, ticks = identity.get("pid"), identity.get("start_ticks")
    if not isinstance(pid, int) or not isinstance(ticks, int):
        raise ValueError("exact launch identity PID and start ticks are required")
    stat_path = Path("/proc") / str(pid) / "stat"
    if not stat_path.exists():
        return
    fields = stat_path.read_text(encoding="utf-8").rpartition(") ")[2].split()
    if len(fields) <= 19 or int(fields[19]) != ticks:
        raise ValueError("batch PID identity changed")
    if fields[0] != "Z":
        raise ValueError("batch controller remains live")


def gpu_idle() -> None:
    if LOCK.exists() or LOCK.is_symlink():
        raise ValueError("GPU lock remains")
    result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                            check=True, text=True, capture_output=True, timeout=30)
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not values or any(int(value) >= 1000 for value in values):
        raise ValueError("GPU is not idle")


def raw_files(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): sha(path) for path in sorted(directory.rglob("*")) if path.is_file()}


def service_evidence(directory: Path, status: Path, final_verdict: str) -> tuple[dict, dict]:
    """Declare every actual arm; only failed startup may lack serve_args.txt."""
    markers = {"SERVE_CMD.txt", "ENV.txt", "serve.log", "serve_args.txt", "compiled_extensions.json"}
    arms, missing = {}, []
    status_doc = load(status)
    for arm in sorted(path for path in directory.iterdir() if path.is_dir()
                      and any((path / name).exists() for name in markers)):
        required = ("SERVE_CMD.txt", "ENV.txt", "serve.log", "compiled_extensions.json")
        for name in required:
            regular(arm / name)
        files = {name: sha(arm / name) for name in (*required, "serve_args.txt") if (arm / name).is_file()}
        if "serve_args.txt" not in files:
            if final_verdict != "failed_harness" or status_doc.get("state") not in {"failed", "error"}:
                raise ValueError("only failed harness startup may lack serve_args.txt")
            error = status_doc.get("error")
            if not isinstance(error, str) or not error.strip():
                raise ValueError("missing serve_args requires terminal startup error")
            evidence = []
            for path in (arm / "SERVE_CMD.txt", arm / "serve.log", status):
                evidence.append({"path": path.relative_to(directory).as_posix(), "sha256": sha(path)})
            missing.append({"arm": arm.name, "reason": error, "evidence": evidence})
        arms[arm.name] = {"files": files}
    if not arms:
        raise ValueError("measured continuation round has no declared service arms")
    return arms, {"missing_serve_args": missing}


def validate_stage(stage: Path) -> tuple[dict, str]:
    stage = Path(stage)
    if stage.is_symlink() or not stage.is_dir() or stage.stat().st_mode & 0o222:
        raise ValueError("immutable auditor stage required")
    report_path = stage / "cpu_validation.json"
    regular_readonly(report_path)
    report = load(report_path)
    if (report.get("schema") != STAGE_SCHEMA or report.get("verdict") != "PASS"
            or report.get("gpu_started") is not False or report.get("requests_sent") is not False):
        raise ValueError("auditor stage is not a CPU-only PASS")
    if report.get("d04_tools") != TOOLS:
        raise ValueError("auditor stage does not bind canonical D04 tools")
    files = report.get("files")
    if not isinstance(files, dict) or not STAGE_FILES <= set(files):
        raise ValueError("auditor stage source map incomplete")
    for name, digest in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe auditor stage path")
        path = stage / relative
        regular_readonly(path)
        if not isinstance(digest, str) or sha(path) != digest:
            raise ValueError("auditor stage source changed: " + name)
    if sha(HERE / "t17_continuation_close.py") != files["t17_continuation_close.py"]:
        raise ValueError("closer differs from its frozen CPU-tested source")
    step = report.get("step", {})
    log = stage / "regression.log"
    if (not isinstance(step, dict) or step.get("returncode") != 0 or not isinstance(step.get("log_sha256"), str)
            or not log.is_file() or sha(log) != step["log_sha256"]):
        raise ValueError("auditor stage regression proof differs")
    return report, sha(report_path)


def frozen_auditor(stage: Path, report: dict) -> ModuleType:
    source = stage / "t17_continuation_review.py"
    spec = importlib.util.spec_from_file_location("ft_t17_frozen_continuation_auditor", source)
    if spec is None or spec.loader is None:
        raise ValueError("frozen continuation auditor is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdict_of(audit: dict) -> str:
    verdict = audit.get("verdict")
    mapping = {"kept_pending_independent_review": "kept", "not_met": "not_met", "failed_harness": "failed_harness"}
    if verdict not in mapping:
        raise ValueError("frozen independent auditor did not reach a closable verdict")
    return mapping[verdict]


def audit(round_dir: Path, review_stage: Path, review_json: Path, launch_identity: Path) -> dict:
    directory = Path(round_dir)
    if directory.name not in {"E2-R033", "E2-R034", "E2-R034a", "E2-R035", "E2-R036", "E2-R037", "E2-R038", "E2-R039"}:
        raise ValueError("only allocated formal T17 rounds E2-R033 through E2-R039 (plus R034a) can be closed")
    no_symlinks(directory)
    if any((directory / name).exists() for name in ("round.json", "round_history", "MANIFEST.sha256")):
        raise ValueError("round is already sealed")
    report, stage_sha = validate_stage(Path(review_stage))
    identity = load(Path(launch_identity))
    if not {"pid", "start_ticks", "pgid", "launch_receipt_sha256"} <= set(identity):
        raise ValueError("launch identity fields are incomplete")
    receipt_path = LAUNCH_RECEIPTS / ("launch_" + directory.name + ".json")
    receipt = load(receipt_path)
    if (receipt.get("state") != "launched" or receipt.get("rid") != directory.name
            or not isinstance(receipt.get("batch"), int) or receipt.get("batch_pid") != identity["pid"]
            or receipt.get("batch_pgid") != identity["pgid"] or sha(receipt_path) != identity["launch_receipt_sha256"]):
        raise ValueError("exact launched batch identity required")
    status = directory / ("status_batch" + str(receipt["batch"]) + ".json")
    status_doc = load(status)
    if (status_doc.get("rid") != directory.name or status_doc.get("batch") != receipt["batch"]
            or status_doc.get("batch_pid") != identity["pid"]):
        raise ValueError("terminal status differs from launch identity")
    terminal(identity)
    reviewer = frozen_auditor(Path(review_stage), report)
    recomputed = reviewer.audit(directory, receipt_path, status)
    saved = load(Path(review_json))
    if saved != recomputed:
        raise ValueError("independent audit JSON differs from frozen recomputation")
    if (recomputed.get("schema") != "ft_t17_continuation_independent_audit/v1"
            or recomputed.get("launch_receipt_sha256") != sha(receipt_path)
            or recomputed.get("actual_status_sha256") != sha(status)):
        raise ValueError("frozen independent audit binding is incomplete")
    if report.get("audit_sha256") != sha(Path(review_json)):
        raise ValueError("auditor stage does not bind independent audit JSON")
    final_verdict = verdict_of(recomputed)
    arms, failure_archive = service_evidence(directory, status, final_verdict)
    batch_log = Path(receipt.get("batch_log", ""))
    regular(batch_log)
    return {"directory": directory, "receipt": receipt, "status": status_doc, "status_path": status,
            "stage": Path(review_stage), "stage_report": report, "stage_report_sha256": stage_sha,
            "review": recomputed, "review_path": Path(review_json), "review_sha256": sha(Path(review_json)),
            "launch_identity": Path(launch_identity),
            "launch_receipt_path": receipt_path,
            "service_arms": arms, "failure_archive": failure_archive,
            "batch_log": batch_log, "batch_log_sha256": sha(batch_log),
            "original_raw_files": raw_files(directory), "final_verdict": final_verdict}


def verify_tools() -> dict[str, bytes]:
    result = {}
    for name, digest in TOOLS.items():
        path = ROOT / "scripts" / name
        regular(path)
        if sha(path) != digest:
            raise ValueError("canonical D04 source differs: " + name)
        result[name] = path.read_bytes()
    return result


def metadata(packet: dict) -> dict:
    receipt, review = packet["receipt"], packet["review"]
    return {"schema": "ft_round/v2", "round_id": receipt["rid"], "epoch": 2, "card": "T17",
            "title": "T17 continuation measurement", "parent": "E2-R032-gate-D14",
            "base": {"commit": PARENT, "code_version": "D14-parent@e4f3202"},
            "experimental": {"candidate_commit": receipt.get("candidate_commit")}, "serve": {"arms": packet["service_arms"]},
            "design": {"batch": receipt["batch"]}, "results": review,
            "proposed_verdict": packet["final_verdict"], "verdict": "pending_review", "verdict_history": [], "retractions": [],
            "independent_review_sha256": packet["review_sha256"],
            "acceptance_limits": ["Only the frozen continuation input matrix and independently recomputed raw evidence are closed.",
                                  "A not_met or failed_harness result does not authorize an acceptance override."],
            "failure_archive": packet["failure_archive"],
            "batch_logs": [{"path": str(packet["batch_log"]), "sha256": packet["batch_log_sha256"]}],
            "diagnostics": {"independent_audit_sha256": packet["review_sha256"],
                            "auditor_stage_report_sha256": packet["stage_report_sha256"],
                            "launch_identity_sha256": sha(packet["launch_identity"]),
                            "launch_receipt_sha256": sha(packet["launch_receipt_path"]),
                            "original_raw_files": packet["original_raw_files"]}}


def verify_manifest(directory: Path, must_include: set[str]) -> None:
    manifest = directory / "MANIFEST.sha256"
    regular_readonly(manifest)
    names = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ./")
        path = directory / name
        if not separator or len(digest) != 64 or not path.is_file() or sha(path) != digest:
            raise ValueError("D04 manifest no longer binds archived file")
        names.add(name)
    if not must_include <= names:
        raise ValueError("D04 manifest omits original evidence or launch identity")


def close(round_dir: Path, review_stage: Path, review_json: Path, launch_identity: Path, *, execute: bool = False) -> dict:
    packet = audit(round_dir, review_stage, review_json, launch_identity)
    if not execute:
        return {"state": "audit_first_only", "verdict": packet["final_verdict"], "rid": packet["receipt"]["rid"]}
    tools = verify_tools()
    gpu_idle()
    directory = packet["directory"]
    # ``batch.sh`` and ``source_tools`` were written by the measured runner and
    # are deliberately never copied or replaced by this closure.
    review_name = "review_batch" + str(packet["receipt"]["batch"]) + ".json"
    # Archive the independently supplied bytes, rather than re-serializing the
    # object, so the stage-pinned review SHA remains meaningful in the round.
    xwrite(directory / review_name, Path(review_json).read_bytes())
    xwrite(directory / "launch_identity.json", Path(launch_identity).read_bytes())
    xwrite(directory / "launch_receipt.json", packet["launch_receipt_path"].read_bytes())
    for path in packet["stage"].rglob("*"):
        if path.is_symlink():
            raise ValueError("auditor stage archive symlink")
        if path.is_file():
            xwrite(directory / "close_source" / path.relative_to(packet["stage"]), path.read_bytes())
    for name, data in tools.items():
        xwrite(directory / name, data)
    xwrite(directory / "round.json", encoded(metadata({**packet, "launch_identity": Path(launch_identity)})))
    subprocess.run(["bash", str(directory / "round_close.sh"), packet["receipt"]["rid"], "--round-root", str(directory.parent)], check=True,
                   env={**os.environ, "FT_ROUND_PYTHON": sys.executable})
    subprocess.run([sys.executable, str(directory / "round_json_append.py"), str(directory), "verdict", "--new", packet["final_verdict"],
                    "--reason", "Frozen independent continuation audit recomputed the measured raw evidence.",
                    "--evidence", review_name, "launch_identity.json",
                    "--by", "authorized T17 continuation D04 closer"], check=True)
    subprocess.run([sys.executable, str(directory / "round_json_append.py"), str(directory), "check"], check=True)
    if any(sha(directory / name) != digest for name, digest in packet["original_raw_files"].items()):
        raise ValueError("closure changed original raw evidence")
    verify_manifest(directory, set(packet["original_raw_files"]) | {"launch_identity.json", "launch_receipt.json", review_name})
    if any(path.stat().st_mode & 0o222 for path in (directory, *directory.rglob("*"))):
        raise ValueError("closed continuation round remains writable")
    return {"rid": packet["receipt"]["rid"], "batch": packet["receipt"]["batch"], "verdict": packet["final_verdict"],
            "round_sha256": sha(directory / "round.json"), "manifest_sha256": sha(directory / "MANIFEST.sha256"),
            "original_raw_files_verified": len(packet["original_raw_files"])}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=Path, required=True)
    parser.add_argument("--review-stage", type=Path, required=True)
    parser.add_argument("--review-json", type=Path, required=True)
    parser.add_argument("--launch-identity", type=Path, required=True)
    parser.add_argument("--close", action="store_true")
    args = parser.parse_args(argv)
    if args.close and sys.platform != "linux":
        raise SystemExit("actual D04 closure requires the Linux evidence host")
    print(json.dumps(close(args.round, args.review_stage, args.review_json, args.launch_identity, execute=args.close), sort_keys=True))


if __name__ == "__main__":
    main()
