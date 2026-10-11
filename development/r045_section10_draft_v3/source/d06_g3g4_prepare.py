#!/usr/bin/env python3
"""Prepare the queued D06 E2-R042 G3/G4 development self-check.

Without --run this performs no server, socket connection, GPU or lock action.
The Linux-only --run path uses a fresh loopback fixture port; it never uses
8095.  Its output is development evidence, not T05/T16/scientific acceptance.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path("/data2/FreeToken")
WORKTREE = ROOT / "wt/e2base1-ordinary-rewind"
VENV = ROOT / "venv"
RUNS = ROOT / "runs/dev_D06"
LOCK = Path("/data2/_shared/gpu.lock")
RID = "E2-R042"
CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"
T20_RID = "E2-R040"
D07_RID = "E2-R043"
T06_RID = "E2-R046"
T06_SEED_SHA256 = {
    "seed12k": "1bcb7214c78f16258c8689e8f57f2d72f0930f9924c58ae1a18763e18c364153",
    "seed_45k": "499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9",
    "seed_real": "8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3",
}
MODEL = "Qwen3.8-Flash-Next-NVFP4"
MODEL_PATH = ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"
PROBE = Path("scripts/multisession_probe.py")
G3_REFERENCE_TPS = 31.7
G3_BOUNDS = (G3_REFERENCE_TPS * 0.8, G3_REFERENCE_TPS * 1.2)
LOG_TIME = re.compile(r"\[(\d{4}-\d\d-\d\d)\|(\d\d:\d\d:\d\d)\|")
BATCH_LINE = re.compile(r"\b(?:Prefill|Decode) batch\b")
OWNED_SOURCE = ROOT / "runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools"
OWNED_PROTOCOL_SHA = "7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf"
ATOMIC_HELPER_SHA = "a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf"
D07_GATE_SOURCE = Path(__file__).with_name("d07_g3g4_prepare.py")
PAUSE_SOURCE_NAMES = ("r055b_pause_harness_v2.py", "r055b_owned_launch.py", "r055_owned_launch.py")
HARNESS_VERSION = "r045-section10-v3"
LOCK_TOKEN: str | None = None
LOCK_INODE: int | None = None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def fixture_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as guard:
        guard.bind(("127.0.0.1", 0))
        port = guard.getsockname()[1]
    if not 1024 <= port <= 65535:
        raise RuntimeError("loopback socket guard did not allocate an ephemeral port")
    return port


def checked_worktree(worktree: Path) -> dict:
    if worktree.is_symlink():
        raise RuntimeError("E2-base.1 worktree must not be a symlink")
    head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != CANDIDATE or dirty:
        raise RuntimeError(f"D06 requires clean E2-base.1@{CANDIDATE}")
    probe = worktree / PROBE
    blob = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", f"{CANDIDATE}:{PROBE.as_posix()}"], text=True).strip()
    actual, normalized = sha256(probe), lf_sha256(probe)
    # Git object IDs are SHA-1 in this repository.  Compare bytes through git,
    # retaining both local forms because Windows checkout conversion is expected.
    expected = subprocess.check_output(["git", "-C", str(worktree), "show", f"{CANDIDATE}:{PROBE.as_posix()}"], stderr=subprocess.DEVNULL)
    expected_sha = hashlib.sha256(expected).hexdigest()
    if expected_sha != actual:
        raise RuntimeError("candidate multisession wrapper bytes do not match its Git blob")
    return {"worktree": str(worktree), "commit": head, "tracked_clean": True,
            "probe_git_blob": blob, "probe_raw_sha256": actual,
            "probe_lf_sha256": normalized, "probe_git_blob_sha256": expected_sha}


def require_kept(rid: str) -> Path:
    return _d07_closed_round_gate().require_closed_round(rid, "kept")


def _d07_closed_round_gate():
    if D07_GATE_SOURCE.is_symlink() or not D07_GATE_SOURCE.is_file():
        raise RuntimeError("D06 closed-round gate source is unavailable")
    spec = importlib.util.spec_from_file_location("d06_closed_round_gate", D07_GATE_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def require_t06_measured() -> Path:
    closure = _d07_closed_round_gate().require_closed_round(T06_RID, "measured")
    document = json.loads(closure.read_text(encoding="utf-8"))
    base = document.get("base", {})
    manifest = closure.with_name("MANIFEST.sha256")
    if (document.get("schema") != "ft_round/v2" or document.get("verdict") != "measured"
            or document.get("proposed_verdict") != "measured" or document.get("epoch") != 2
            or base.get("commit") != CANDIDATE or manifest.is_symlink() or not manifest.is_file()):
        raise RuntimeError("T06 closure is not the required E2-base.1 measured round")
    packet = closure.with_name("manifest.json")
    if packet.is_symlink() or not packet.is_file():
        raise RuntimeError("T06 route evidence manifest is absent")
    evidence = json.loads(packet.read_text(encoding="utf-8"))
    arms = evidence.get("arms")
    if evidence.get("schema") != "ft_t06_route_manifest/v1" or evidence.get("candidate_commit") != CANDIDATE or evidence.get("rid") != T06_RID or not isinstance(arms, list):
        raise RuntimeError("T06 route evidence manifest identity differs")
    _verify_t06_manifest_metadata(evidence)
    return closure


def _verify_t06_manifest_metadata(evidence: dict) -> None:
    """Only small T06 manifest metadata belongs in a downstream startup gate."""
    arms = evidence.get("arms", [])
    roles = {arm.get("role") for arm in arms if isinstance(arm, dict)}
    if (len(arms) != 4 or roles != {"seed12k", "seed_45k", "seed_real", "two"}
            or evidence.get("d15_training_route") != "G_seed12k/route"
            or set(evidence.get("heldout_routes", [])) != {"G_seed_45k/route", "G_seed_real/route", "G_two/route"}):
        raise RuntimeError("T06 route evidence manifest arm metadata differs")


def _verify_t06_manifest(root: Path, evidence: dict) -> None:
    arms = evidence.get("arms", [])
    seeds = {"seed12k", "seed_45k", "seed_real"}
    generated = [arm for arm in arms if isinstance(arm, dict) and arm.get("role") in seeds]
    two = [arm for arm in arms if isinstance(arm, dict) and arm.get("role") == "two"]
    if (len(arms) != 4 or len(generated) != 3 or {arm["role"] for arm in generated} != seeds
            or len(two) != 1 or any(arm.get("rounds") != 12 or arm.get("max_tokens") != 2048 for arm in generated)
            or two[0].get("same_prompt") is not False):
        raise RuntimeError("T06 route evidence manifest lacks the required three real traces and distinct two-decode")
    def member(relative):
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise RuntimeError("T06 evidence path is unsafe")
        path = root / relative
        if path.is_symlink() or root.resolve() not in path.resolve().parents:
            raise RuntimeError("T06 evidence path escapes its round")
        return path
    if evidence.get("d15_training_route") != "G_seed12k/route" or set(evidence.get("heldout_routes", [])) != {"G_seed_45k/route", "G_seed_real/route", "G_two/route"}:
        raise RuntimeError("T06 training route must be only G_seed12k; heldout routes differ")
    independent = evidence.get("service", {}).get("independent_arms")
    if independent != ["G_seed12k", "G_seed_45k", "G_seed_real", "G_two"]:
        raise RuntimeError("T06 must bind four independent service arms")
    files = evidence.get("files", {})
    required = {f"{seed}_{name}" for seed in seeds for name in ("serve_log", "trace", "seed_binding", "route_summary")}
    required |= {f"two_{name}" for name in ("serve_log", "two_decode", "route_summary")}
    if not isinstance(files, dict) or not required.issubset(files):
        raise RuntimeError("T06 trace/seed/analysis evidence is incomplete")
    for name in required:
        row = files[name]
        path = member(row.get("path"))
        if not path.is_file() or sha256(path) != row.get("sha256"):
            raise RuntimeError("T06 raw evidence SHA differs: " + name)
    for arm in generated:
        role = arm["role"]
        if (arm.get("directory") != f"G_{role}" or arm.get("d15_training_input") is not (role == "seed12k")
                or arm.get("seed_raw_sha256") != T06_SEED_SHA256[role]):
            raise RuntimeError("T06 seed arm directory/training partition differs")
        route = member(f"G_{role}/route")
        if not route.is_dir() or not any(route.iterdir()):
            raise RuntimeError("T06 seed route evidence is empty: " + role)
        for key in ("serve_log", "trace", "seed_binding", "route_summary"):
            row = files[f"{role}_{key}"]
            expected = {"serve_log": f"G_{role}/serve.log", "trace": f"G_{role}/trace_{role}.json",
                        "seed_binding": f"G_{role}/trace_{role}.seed_binding.json", "route_summary": f"route_summary_{role}.json"}[key]
            if row.get("path") != expected or arm.get(key) != expected or arm.get(key + "_sha256") != row.get("sha256"):
                raise RuntimeError("T06 seed arm binding differs")
        binding = json.loads(member(f"G_{role}/trace_{role}.seed_binding.json").read_text(encoding="utf-8"))
        if binding.get("seed_raw_sha256") != T06_SEED_SHA256[role] or not binding.get("actual_wire_first_content_sha256"):
            raise RuntimeError("T06 seed raw/wire binding differs")
    arm = two[0]
    if arm.get("directory") != "G_two" or arm.get("d15_training_input") is not False:
        raise RuntimeError("T06 two-decode arm directory/training partition differs")
    route = member("G_two/route")
    if not route.is_dir() or not any(route.iterdir()):
        raise RuntimeError("T06 two-decode route evidence is empty")
    for key in ("serve_log", "route_summary"):
        row = files[f"two_{key}"]
        if arm.get(key) != row["path"] or arm.get(key + "_sha256") != row["sha256"]:
            raise RuntimeError("T06 two-decode arm binding differs")
    row = files["two_two_decode"]
    if arm.get("result") != row["path"] or arm.get("sha256") != row["sha256"]:
        raise RuntimeError("T06 two-decode result binding differs")


def require_d07_g3g4_result() -> tuple[Path, Path]:
    root = ROOT / "runs/dev_D07"
    valid: list[tuple[Path, Path]] = []
    for result in root.glob("E2-R043_*/result.json"):
        cleanup = result.with_name("owned_cleanup.json")
        if result.is_symlink() or cleanup.is_symlink() or not cleanup.is_file():
            continue
        try:
            receipt, stopped = json.loads(result.read_text(encoding="utf-8")), json.loads(cleanup.read_text(encoding="utf-8"))
            g3, g4 = receipt.get("g3", {}), receipt.get("g4", {})
            if (receipt.get("schema") == "ft_d07_g3g4_result/v1" and receipt.get("verdict") == "development_selfcheck_pass"
                    and receipt.get("development_selfcheck_not_acceptance") is True and receipt.get("rid") == D07_RID
                    and receipt.get("candidate_commit") == CANDIDATE and g3.get("same_cold_id") is True
                    and g3.get("byte_identical") is True and g4.get("uid_bound") is True
                    and type(g4.get("suffix_tokens")) is int and g4["suffix_tokens"] > 0
                    and receipt.get("cuda_graph_disabled_marker") is True and stopped.get("schema") == "ft_d07_owned_cleanup/v1"
                    and stopped.get("rid") == D07_RID and stopped.get("batch") == receipt.get("batch")
                    and stopped.get("candidate_commit") == CANDIDATE and stopped.get("gpu_owner") == receipt.get("gpu_owner")
                    and stopped.get("lock_released") is True):
                valid.append((result, cleanup))
        except (OSError, ValueError, TypeError):
            continue
    if len(valid) != 1:
        raise RuntimeError(f"D07 requires exactly one complete E2-R043 development receipt, found {len(valid)}")
    return valid[0]


def load_owned_lifecycle(source: Path = OWNED_SOURCE):
    protocol = source / "t17_owned_launch_protocol.py"
    if protocol.is_symlink() or sha256(protocol) != OWNED_PROTOCOL_SHA:
        raise RuntimeError("pinned owned lifecycle source differs")
    spec = importlib.util.spec_from_file_location("d06_owned_lifecycle", protocol)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # The frozen protocol predates this /proc birth API. R046 validates the
    # adapter against that same protocol and a real private process group.
    module.process_identity = _d07_closed_round_gate().process_identity
    return module


def acquire_gpu_lock(batch: int) -> dict:
    """Atomically own the GPU lock in the child that will use the GPU."""
    global LOCK_TOKEN, LOCK_INODE
    birth = load_owned_lifecycle().process_identity(os.getpid())
    if birth is None or birth.get("pid") != os.getpid() or type(birth.get("start_ticks")) is not int:
        raise RuntimeError("D06 GPU child birth cannot be established")
    owner = {"owner": "dev_D06_G3_G4", "rid": RID, "batch": batch, "birth": birth, "since": time.time()}
    token = json.dumps(owner, sort_keys=True)
    try:
        descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise RuntimeError("foreign GPU lock exists; D06 remains queued") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(token)
        stream.flush()
        os.fsync(stream.fileno())
    LOCK_TOKEN, LOCK_INODE = token, LOCK.stat().st_ino
    return owner


def require_gpu_idle() -> list[int]:
    values = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True).splitlines()
    used = [int(value.strip()) for value in values if value.strip()]
    if not used or any(value >= 1000 for value in used):
        raise RuntimeError(f"GPU is not idle after acquiring D06 lock: {used}")
    return used


def release_gpu_lock() -> None:
    global LOCK_TOKEN, LOCK_INODE
    if LOCK_TOKEN is None or LOCK_INODE is None:
        return
    if (not LOCK.exists() or LOCK.is_symlink() or LOCK.stat().st_ino != LOCK_INODE
            or LOCK.read_text(encoding="utf-8") != LOCK_TOKEN):
        raise RuntimeError("D06 refuses to release a foreign/replaced GPU lock")
    LOCK.unlink()
    LOCK_TOKEN = LOCK_INODE = None


def environment(worktree: Path, d0: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("FT_", "R055")) or key in {"PYTHONPATH", "CUDA_VISIBLE_DEVICES"}:
            env.pop(key)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", PYTHONPATH=str(worktree / "python"),
               VIRTUAL_ENV=str(VENV), PATH=str(VENV / "bin") + ":" + env.get("PATH", ""),
               CUDA_VISIBLE_DEVICES="0", FT_DEV_PAUSE_ENDPOINT="1", FT_DEV_D0="1",
               FT_DEV_D0_PATH=str(d0), FT_DEV_D0_TIMELINE="1", FT_DEV_D0_TIMELINE_STEPS="20000")
    env.update(R055_PAUSE_OBSERVATIONS=str(d0.parent / "pause_observations.jsonl"),
               R055B_MODEL_MEMORY=str(d0.parent / "model_process_cuda.jsonl"))
    return env


def pause_module(name: str):
    """Load the reviewed repair/observer without invoking its R055 launch path."""
    if name not in PAUSE_SOURCE_NAMES:
        raise ValueError("unregistered pause harness source")
    source = Path(__file__).with_name(name)
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("pause harness source unavailable: " + name)
    spec = importlib.util.spec_from_file_location("d06_" + source.stem, source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def prepare_service_files(run_dir: Path, worktree: Path, port: int) -> tuple[dict, list[str]]:
    """Both the formal service and filesystem dry-run execute this writer."""
    owner, repair = pause_module("r055b_owned_launch.py"), pause_module("r055b_pause_harness_v2.py")
    observer = repair.corrected_observer(owner)
    startup = owner.PAUSE_STARTUP.replace("import r055b_pause_observer\nr055b_pause_observer.install()",
        "import d06_pause_observer_v3\nd06_pause_observer_v3.install()")
    if startup == owner.PAUSE_STARTUP:
        raise RuntimeError("pause startup import contract differs")
    for name, content in (("d06_pause_observer_v3.py", observer), ("d06_pause_startup_v3.py", startup)):
        path = run_dir / name
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        path.chmod(0o444)
    env = environment(worktree, run_dir / "d0")
    if type(port) is not int or not 1024 <= port <= 65535 or port == 8095:
        raise ValueError("D06 observer requires its owned dynamic loopback port")
    protocol_argv = serve_argv(port)
    if protocol_argv[protocol_argv.index("--memory-ratio") + 1] != "0.88":
        raise RuntimeError("R045 G3/G4 and performance must retain memory-ratio 0.88")
    argv = [str(VENV / "bin/python"), str(run_dir / "d06_pause_startup_v3.py"), *protocol_argv[1:]]
    write_new(run_dir / "SERVE_CMD.json", {"argv": argv, "protocol_argv": protocol_argv, "port": port,
        "harness_version": HARNESS_VERSION,
        "pause_source_sha256": {name: sha256(Path(__file__).with_name(name)) for name in PAUSE_SOURCE_NAMES},
        "environment": {key: env[key] for key in ("CUDA_VISIBLE_DEVICES", "FT_DEV_PAUSE_ENDPOINT", "FT_DEV_D0",
            "FT_DEV_D0_PATH", "FT_DEV_D0_TIMELINE", "FT_DEV_D0_TIMELINE_STEPS", "PYTHONPATH", "VIRTUAL_ENV",
            "R055_PAUSE_OBSERVATIONS", "R055B_MODEL_MEMORY")}})
    return env, argv


def summarize_model_memory(run_dir: Path) -> dict:
    """Bind real model-process samples and every complete UserMsg request pair."""
    path = run_dir / "model_process_cuda.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    owned = json.loads((run_dir / "owned_process.json").read_text(encoding="utf-8"))
    birth = {key: owned["birth"][key] for key in ("pid", "start_ticks", "execution_id", "pgid", "session")}
    loaded = [row for row in rows if row.get("event") == "model_loaded"]
    if len(loaded) != 1:
        raise RuntimeError("D06 model-loaded CUDA sample missing or ambiguous")
    worker = loaded[0]["worker_birth"]
    for row in rows:
        if (row.get("schema") != "ft_r055b_model_process_cuda/v1" or row.get("device") != 0
                or row.get("service_birth") != birth or row.get("worker_birth") != worker
                or row.get("error") is not None or "error" in str(row.get("event"))):
            raise RuntimeError("D06 model-process CUDA identity or error sample differs")
        for key in ("free_bytes", "total_bytes", "driver_used_bytes", "current_allocated_bytes",
                    "current_reserved_bytes", "cumulative_allocated_peak_bytes", "cumulative_reserved_peak_bytes", "time_ns"):
            if type(row.get(key)) is not int or row[key] < 0:
                raise RuntimeError("D06 model-process CUDA sample is incomplete")
        if row["free_bytes"] > row["total_bytes"] or row["driver_used_bytes"] != row["total_bytes"] - row["free_bytes"]:
            raise RuntimeError("D06 model-process CUDA byte accounting differs")
    if len({row["total_bytes"] for row in rows}) != 1:
        raise RuntimeError("D06 CUDA device total changed")
    before, after = ([row for row in rows if row["event"] == event] for event in ("request_before", "request_after"))
    uids = {row["uid"] for row in before}
    if (not before or None in uids or len(uids) != len(before) or len(after) != len(before)
            or {row["uid"] for row in after} != uids):
        raise RuntimeError("D06 UserMsg request-before/after boundaries incomplete")
    for row in before:
        end = next(value for value in after if value["uid"] == row["uid"])
        if row["time_ns"] >= end["time_ns"]:
            raise RuntimeError("D06 request-before/after timestamps reversed")
    return {"schema": "ft_r045_model_memory_summary/v1", "complete": True, "harness_version": HARNESS_VERSION,
            "service_birth": birth, "worker_birth": worker, "request_count": len(before),
            "memory_jsonl": str(path), "memory_jsonl_sha256": sha256(path), "events": rows,
            "min_free_bytes": min(row["free_bytes"] for row in rows),
            "total_bytes": loaded[0]["total_bytes"],
            "maximum_sampled_driver_used_bytes": max(row["driver_used_bytes"] for row in rows),
            "cumulative_allocated_peak_bytes": max(row["cumulative_allocated_peak_bytes"] for row in rows),
            "cumulative_reserved_peak_bytes": max(row["cumulative_reserved_peak_bytes"] for row in rows),
            "peak_scope": "Torch cumulative allocator peaks; driver use is sampled total-free."}


def run_pause_chain(run_dir: Path, worktree: Path, port: int) -> dict:
    """Exercise accepted pause, timed-out pending cancel, and a real resumed cold request."""
    gate, repair = _d07_closed_round_gate(), pause_module("r055b_pause_harness_v2.py")
    windows = {}
    for prefix in ("before", "after_cancel"):
        if prefix == "after_cancel":
            normal = repair.pause_request(port, 1.0, 5.0)
            write_new(run_dir / "pause_completed.json", normal)
            cancel = repair.pause_request(port, 30.0, 0.05)
            write_new(run_dir / "pause_cancel.json", cancel)
            if (normal.get("status") != "accepted" or not isinstance(normal.get("request_id"), str)
                    or not normal["request_id"] or cancel.get("status") != "timeout"
                    or not isinstance(cancel.get("request_id"), str) or not cancel["request_id"]
                    or cancel["request_id"] == normal["request_id"] or "cancel enqueue" in str(cancel.get("error", ""))):
                raise RuntimeError("D06 pause/cancel API receipt is unbound")
        start = time.time_ns()
        cold_id = RID + ("-pause-before" if prefix == "before" else "-pause-after-cancel")
        path = run_dir / (prefix + ".json")
        gate.invoke_cold_eq(worktree, port, cold_id, path)
        windows[prefix] = (start, time.time_ns())
        case = json.loads(path.read_text(encoding="utf-8")); record = case.get("record", {})
        if (record.get("cold_id") != cold_id or record.get("built_tokens") != 32052 or record.get("prompt_tokens") != 32064
                or record.get("completion_tokens") != 128 or record.get("cached_tokens") != 0
                or record.get("finish_reason") != "length" or case.get("events") != 128 or not case.get("text")):
            raise RuntimeError("D06 pause-chain cold request changed the original 32K/128 protocol")
    backend = pause_module("r055_owned_launch.py")._trace_pause_backend(run_dir, normal["request_id"], cancel["request_id"])
    memory = summarize_model_memory(run_dir)
    for prefix, (start, end) in windows.items():
        before = [row for row in memory["events"] if row["event"] == "request_before" and start <= row["time_ns"] <= end]
        after = [row for row in memory["events"] if row["event"] == "request_after" and start <= row["time_ns"] <= end]
        if len(before) != 1 or len(after) != 1 or before[0]["uid"] != after[0]["uid"]:
            raise RuntimeError("D06 cold request is not bound to a complete UserMsg memory pair: " + prefix)
    for event, request_id in (("pause_before", normal["request_id"]), ("pause_after", normal["request_id"]),
                              ("cancel_before", cancel["request_id"]), ("cancel_after", cancel["request_id"])):
        if len([row for row in memory["events"] if row["event"] == event and row.get("request_id") == request_id]) != 1:
            raise RuntimeError("D06 CUDA control boundary incomplete: " + event)
    write_new(run_dir / "cuda_memory_summary.json", memory)
    result = {"schema": "ft_r045_d06_pause_chain/v1", "complete": True, "backend_evidence": backend,
              "pause_request_id": normal["request_id"], "cancel_request_id": cancel["request_id"],
              "cold_request_windows_ns": windows, "cuda_memory_summary": memory}
    write_new(run_dir / "pause_chain.json", result)
    return result


def serve_argv(port: int) -> list[str]:
    return [str(VENV / "bin/ft"), "serve", "--model-path", str(MODEL_PATH), "--served-model-name", MODEL,
            "--host", "127.0.0.1", "--port", str(port), "--memory-ratio", "0.88", "--moe-cache-auto",
            "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
            "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2", "--cuda-graph-max-bs", "2",
            "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--max-prefill-length", "4096",
            "--enable-cache-report", "--enable-special-token-ckpt", "--tool-call-parser", "qwen3_coder",
            "--reasoning-parser", "qwen3", "--prefill-layer-major", "--mamba-host-slots", "0"]


def start_server(run_dir: Path, worktree: Path, port: int) -> subprocess.Popen:
    env, argv = prepare_service_files(run_dir, worktree, port)
    log = (run_dir / "serve.log").open("x", encoding="utf-8")
    process = subprocess.Popen(argv, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        birth = load_owned_lifecycle().process_identity(process.pid)
        if birth is None or birth.get("pgid") != process.pid or birth.get("session") != process.pid:
            raise RuntimeError("owned fixture server did not receive a private PGID/session")
        write_new(run_dir / "owned_process.json", {"pid": process.pid, "pgid": process.pid, "port": port, "birth": birth})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"owned fixture server exited during startup: {process.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    if json.load(response).get("status") == "ok":
                        return process
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise TimeoutError("owned fixture server readiness exceeded 900 seconds")
    except BaseException:
        try:
            load_owned_lifecycle().stop_owned_process(process)
        except BaseException as cleanup_error:
            cleanup_error.owned_process = process
            raise
        raise


def validate_g3(data: dict) -> dict:
    if data.get("schema") != "multisession_probe/v1" or data.get("command") != "two-decode" or data.get("same_prompt") is not True:
        raise ValueError("G3 requires the unchanged same-prompt two-decode schema")
    reps = data.get("reps")
    if not isinstance(reps, list) or len(reps) != 1 or reps[0].get("frontend_token_counts") != [32000, 32000]:
        raise ValueError("G3 requires exactly one actual 32K repetition")
    prompts, ways = reps[0].get("prompt_sha256"), reps[0].get("per_way")
    if not isinstance(prompts, list) or len(prompts) != 2 or prompts[0] != prompts[1] or not isinstance(ways, list) or len(ways) != 2:
        raise ValueError("G3 lacks same-prompt/two-way proof")
    values = []
    for way in ways:
        tps = way.get("decode_tps")
        if type(tps) not in (int, float) or not G3_BOUNDS[0] <= tps <= G3_BOUNDS[1]:
            raise ValueError(f"G3 per-way decode_tps outside {G3_BOUNDS}: {tps!r}")
        if way.get("completion_tokens") != 512:
            raise ValueError("G3 requires 512 acknowledged completion tokens per way")
        sidecar = Path(way.get("token_timestamps", ""))
        events = json.loads(sidecar.read_text(encoding="utf-8")).get("token_events")
        if not isinstance(events, list) or len(events) != 512:
            raise ValueError("G3 ACK sidecar is incomplete")
        for index, event in enumerate(events, 1):
            if event.get("uid") != way.get("uid") or event.get("request_seq") != index or event.get("completion_tokens_delta") != 1 or event.get("completion_tokens_cumulative") != index:
                raise ValueError("G3 ACK sidecar sequence is invalid")
        values.append(tps)
    return {"reference_tps": G3_REFERENCE_TPS, "bounds": list(G3_BOUNDS), "per_way_decode_tps": values}


def batch_lines(log: Path) -> list[dict]:
    rows = []
    for number, text in enumerate(log.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if BATCH_LINE.search(text):
            match = LOG_TIME.search(text)
            if match is None:
                raise ValueError(f"G4 batch line lacks a timestamp: {number}")
            rows.append({"line": number, "wallclock_s": dt.datetime.strptime("|".join(match.groups()), "%Y-%m-%d|%H:%M:%S").timestamp()})
    return rows


def validate_g4(data: dict, log: Path) -> dict:
    if data.get("schema") != "multisession_probe/v1" or data.get("command") != "h1" or len(data.get("reps", [])) != 1:
        raise ValueError("G4 requires exactly one H1 result")
    idle = data["reps"][0].get("idle", {})
    event = idle.get("event", {})
    start, end = event.get("event_start_wallclock_s"), event.get("event_end_wallclock_s")
    pause = event.get("pause", {}).get("response", {})
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start or pause.get("pause_started_wallclock_s") != start or pause.get("deadline_wallclock_s") != end:
        raise ValueError("G4 has no exact ACK-bound idle window")
    evidence = idle.get("evidence", {})
    if evidence.get("event_counters", {}).get("steps") != []:
        raise ValueError("G4 D0 evidence reports scheduler work during idle")
    base = evidence.get("d0_base")
    if not isinstance(base, str):
        raise ValueError("G4 D0 base is absent")
    def rows(suffix: str) -> list[dict]:
        path = Path(base + suffix)
        if not path.is_file():
            raise ValueError(f"G4 D0 evidence missing: {path}")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    steps, prefill = rows("_decode_steps.jsonl"), rows("_prefill.jsonl")
    if any(start <= row.get("t", float("nan")) < end for row in steps) or any(row.get("t_start", float("inf")) < end and row.get("t_end", float("-inf")) > start for row in prefill):
        raise ValueError("G4 exact D0 evidence overlaps idle window")
    overlap = [row for row in batch_lines(log) if start < row["wallclock_s"] < end]
    if overlap:
        raise ValueError(f"G4 serve.log contains Prefill/Decode batch in idle window: {overlap}")
    return {"idle_start_wallclock_s": start, "idle_end_wallclock_s": end, "serve_log_batch_lines": len(batch_lines(log)), "d0_steps_checked": len(steps), "d0_prefill_checked": len(prefill), "log_timestamp_resolution_s": 1}


def packet(worktree: Path) -> dict:
    return {"schema": "ft_d06_g3g4_prepare/v1", "rid": RID, "candidate_commit": CANDIDATE,
            "candidate": checked_worktree(worktree), "output_root": str(RUNS), "fixture_port": fixture_port(),
            "cuda_visible_devices_cpu_guard": "", "run_requires": ["explicit --run", "Linux host", "E2-R041 and E2-R040 D04 kept", "one complete E2-R043 development receipt", "E2-R046 D04 measured", "atomic owned GPU lock"],
            "g3": "two-decode --ctx 32000 --max-tokens 512 --same-prompt 1 --reps 1; each way 31.7 tok/s +/-20%",
            "g4": "h1 --H 1,8,32 --reps 1 --prefill-target 32000; ACK-bound idle window, D0 and real serve.log no batch overlap",
            "development_selfcheck_not_acceptance": True}


def execute(worktree: Path, output_root: Path, *, owned_child: bool = False, batch: int | None = None, launch_receipt: Path | None = None) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("D06 --run requires the Linux GPU host")
    if not owned_child:
        r041, t20 = require_kept("E2-R041-gate-D17"), require_kept(T20_RID)
        d07_result, d07_cleanup = require_d07_g3g4_result()
        t06 = require_t06_measured()
        if LOCK.exists() or LOCK.is_symlink():
            raise RuntimeError("foreign GPU lock exists; D06 remains queued")
        owned = load_owned_lifecycle()
        helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", ATOMIC_HELPER_SHA, "d06_atomic_launcher")
        batch = helper.next_batch(Path("/data2/_shared/runs/ft_rounds"))
        receipt_path = RUNS / f"launch_E2-R042_batch{batch}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        reserved = {"schema": "ft_d06_owned_launch/v1", "state": "reserved", "rid": RID, "batch": batch,
                    "candidate_commit": CANDIDATE, "owned_protocol_sha256": OWNED_PROTOCOL_SHA,
                    "atomic_helper_sha256": ATOMIC_HELPER_SHA,
                    "prerequisites": {"E2-R041-gate-D17": sha256(r041), T20_RID: sha256(t20),
                                      "E2-R043_result": sha256(d07_result), "E2-R043_cleanup": sha256(d07_cleanup), T06_RID: sha256(t06)}}
        gate = _d07_closed_round_gate()
        argv = [str(VENV / "bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child", "--batch", str(batch), "--launch-receipt", str(receipt_path), "--worktree", str(worktree), "--output-root", str(output_root)]
        reserved["argv_sha256"] = gate.argv_sha256(argv); reserved["controller"] = gate.process_birth()
        receipt = owned.reserve_process(helper, batch, RID, argv, receipt_path, reserved)
        child = owned.process_identity(receipt["batch_pid"])
        if child is None or child.get("pid") != receipt["batch_pid"] or type(child.get("start_ticks")) is not int: raise RuntimeError("D06 reserved child birth is unavailable")
        child = {"pid": child["pid"], "start_ticks": child["start_ticks"], "execution_id": f"{child['pid']}:{child['start_ticks']}"}
        return gate.publish_child_binding(receipt_path, receipt, child, lifecycle=owned)
    if batch is None or launch_receipt is None:
        raise RuntimeError("D06 owned child requires its reserved batch")
    gate = _d07_closed_round_gate()
    expected = [str(VENV / "bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child", "--batch", str(batch), "--launch-receipt", str(launch_receipt), "--worktree", str(worktree), "--output-root", str(output_root)]
    gate.require_child_receipt(launch_receipt, batch, worktree, output_root, rid=RID, expected_argv=expected, schema="ft_d06_owned_launch/v1")
    owner = acquire_gpu_lock(batch)
    run_dir = None
    process = None
    try:
        idle_memory_mb = require_gpu_idle()
        r041, t20 = require_kept("E2-R041-gate-D17"), require_kept(T20_RID)
        d07_result, d07_cleanup = require_d07_g3g4_result()
        t06 = require_t06_measured()
        prerequisites = {"E2-R041-gate-D17": r041, T20_RID: t20, "E2-R043_result": d07_result,
                         "E2-R043_cleanup": d07_cleanup, T06_RID: t06}
        closure = r041
        prepared = packet(worktree)
        run_dir = output_root / (RID + "_" + time.strftime("%Y%m%d_%H%M%S"))
        run_dir.mkdir(parents=True)
        shutil.copy2(__file__, run_dir / Path(__file__).name)
        write_new(run_dir / "preflight.json", {**prepared, "r041_closure": str(closure), "r041_closure_sha256": sha256(closure), "gpu_owner": owner, "gpu_idle_memory_mb": idle_memory_mb,
            "prerequisites": {rid: {"path": str(path), "sha256": sha256(path)} for rid, path in prerequisites.items()}})
        port, process = fixture_port(), None
        try:
            process = start_server(run_dir, worktree, port)
            base_url = f"http://127.0.0.1:{port}/v1"
            env = environment(worktree, run_dir / "d0")
            g3_path, g4_path = run_dir / "g3.json", run_dir / "g4.json"
            subprocess.run([str(VENV / "bin/python"), str(worktree / PROBE), "two-decode", "--base-url", base_url, "--model", MODEL, "--ctx", "32000", "--max-tokens", "512", "--same-prompt", "1", "--reps", "1", "--out", str(g3_path)], cwd=worktree, env=env, check=True, timeout=1800)
            g3 = validate_g3(json.loads(g3_path.read_text(encoding="utf-8")))
            subprocess.run([str(VENV / "bin/python"), str(worktree / PROBE), "h1", "--base-url", base_url, "--model", MODEL, "--H", "1,8,32", "--reps", "1", "--prefill-target", "32000", "--out", str(g4_path)], cwd=worktree, env=env, check=True, timeout=1800)
        finally:
            if process is not None:
                load_owned_lifecycle().stop_owned_process(process)
        g4 = validate_g4(json.loads(g4_path.read_text(encoding="utf-8")), run_dir / "serve.log")
        result = {"schema": "ft_d06_g3g4_result/v1", "rid": RID, "candidate_commit": CANDIDATE,
                  "batch": batch, "owner": owner, "verdict": "development_selfcheck_pass",
                  "development_selfcheck_not_acceptance": True, "g3": g3, "g4": g4, "run_dir": str(run_dir)}
        write_new(run_dir / "result.json", result)
        return result
    except BaseException as error:
        process = getattr(error, "owned_process", process)
        if run_dir is not None:
            write_new(run_dir / "failed_harness.json", {"rid": RID, "batch": batch, "owner": owner,
                      "error": repr(error), "development_selfcheck_not_acceptance": True})
        raise
    finally:
        if process is not None and load_owned_lifecycle().owned_group_alive(process.pid):
            raise RuntimeError("D06 owned service remains; preserve GPU lock for recovery")
        release_gpu_lock()
        if run_dir is not None:
            write_new(run_dir / "owned_cleanup.json", {"schema": "ft_d06_owned_cleanup/v1", "rid": RID,
                      "batch": batch, "candidate_commit": CANDIDATE, "owner": owner, "lock_released": True})


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sides = []
        for uid in (1, 2):
            path = root / f"way{uid}.json"
            write_new(path, {"uid": uid, "token_events": [{"uid": uid, "request_seq": n, "completion_tokens_delta": 1, "completion_tokens_cumulative": n} for n in range(1, 513)]})
            sides.append(path)
        g3 = {"schema": "multisession_probe/v1", "command": "two-decode", "same_prompt": True, "reps": [{"frontend_token_counts": [32000, 32000], "prompt_sha256": ["x", "x"], "per_way": [{"uid": uid, "decode_tps": 31.7, "completion_tokens": 512, "token_timestamps": str(path)} for uid, path in zip((1, 2), sides)]}]}
        assert validate_g3(g3)["per_way_decode_tps"] == [31.7, 31.7]
        start, end = dt.datetime(2026, 10, 6, 12, 0, 1).timestamp(), dt.datetime(2026, 10, 6, 12, 0, 2).timestamp()
        base, log = root / "d0", root / "serve.log"
        (root / "d0_decode_steps.jsonl").write_text(json.dumps({"step": 1, "t": start - 1}) + "\n")
        (root / "d0_prefill.jsonl").write_text(json.dumps({"t_start": start - 2, "t_end": start - 1}) + "\n")
        log.write_text("[2026-10-06|12:00:00|engine] Decode batch\n")
        g4 = {"schema": "multisession_probe/v1", "command": "h1", "reps": [{"idle": {"event": {"event_start_wallclock_s": start, "event_end_wallclock_s": end, "pause": {"response": {"pause_started_wallclock_s": start, "deadline_wallclock_s": end}}}, "evidence": {"d0_base": str(base), "event_counters": {"steps": []}}}}]}
        assert validate_g4(g4, log)["serve_log_batch_lines"] == 1
    print("SELFTEST PASS: G3 ACK/TPS bounds and G4 ACK/D0/serve.log idle window")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="explicitly start the queued Linux GPU self-check")
    parser.add_argument("--self-test", action="store_true", help="CPU-only validator test; no service, socket or GPU")
    parser.add_argument("--owned-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--batch", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--launch-receipt", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worktree", type=Path, default=WORKTREE)
    parser.add_argument("--output-root", type=Path, default=RUNS)
    args = parser.parse_args(argv)
    if args.run and args.self_test:
        parser.error("--run and --self-test are exclusive")
    if args.self_test:
        self_test(); return 0
    if args.run:
        print(json.dumps(execute(args.worktree, args.output_root, owned_child=args.owned_child, batch=args.batch, launch_receipt=args.launch_receipt), ensure_ascii=False, sort_keys=True)); return 0
    print(json.dumps(packet(args.worktree), ensure_ascii=False, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
