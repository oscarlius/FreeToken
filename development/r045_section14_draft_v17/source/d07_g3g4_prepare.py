#!/usr/bin/env python3
"""D07 E2-R043 G3/G4 development self-check launcher.

The launcher is deliberately inert unless ``--run`` is supplied on the Linux
host.  It uses an ephemeral loopback port and never contacts 8095.  Its output
under ``/data2/FreeToken/runs/dev_D07`` is development evidence only, never a
T16/T06 or scientific-acceptance result.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import re

ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
WORKTREE = ROOT / "wt/e2base1-ordinary-rewind"
VENV = ROOT / "venv"
RUNS = ROOT / "runs/dev_D07"
LOCK = Path("/data2/_shared/gpu.lock")
CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"
RID = "E2-R043"
T20_RID = "E2-R040"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
MODEL_PATH = ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"
OWNED_SOURCE = ROOT / "runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools"
OWNED_PROTOCOL_SHA = "7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf"
ATOMIC_HELPER_SHA = "a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf"
COLD_RAW_SHA = "1fe95158522da413621e58187c0198f26cf5860b64e3d74dd76df8cfb75a6093"
PROBE_RAW_SHA = "68e6c3f707fc97a6d04e4d9ac2bb582888af5b13b39584e863fe6be649cc306d"
ROUND_WRITER_SHA = "67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lf_normalized_sha256(path: Path) -> str:
    """Match the candidate's LF-pinned bytes when this local checkout is CRLF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def dynamic_fixture_port() -> int:
    """Reserve only an ephemeral loopback fixture port; never probe 8095."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as guard:
        guard.bind(("127.0.0.1", 0))
        port = guard.getsockname()[1]
    if not (1024 <= port <= 65535):
        raise RuntimeError("socket guard did not allocate a valid ephemeral port")
    return port


def checked_worktree(worktree: Path) -> dict:
    if worktree.is_symlink():
        raise RuntimeError("D07 candidate worktree cannot be a symlink")
    head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=no"], text=True
    )
    if head != CANDIDATE or dirty:
        raise RuntimeError("D07 requires clean E2-base.1 candidate 0aa23431e5b800797543bdecbf35a01045131d7d")
    return {"worktree": str(worktree), "commit": head, "tracked_clean": True}


def verify_d07_tools(worktree: Path) -> dict:
    """Fail before GPU allocation if the candidate's D07 client is unimportable."""
    agent = worktree / "scripts/agent_trace.py"
    frozen = worktree / "scripts/_agent_trace_original.py"
    analyzer = worktree / "scripts/route_analyze.py"
    for path in (agent, frozen, analyzer):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"required D07 candidate tool is unavailable: {path}")
    match = re.search(r'^_SHA256\s*=\s*"([0-9a-f]{64})"', agent.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise RuntimeError("D07 agent_trace frozen companion digest is missing")
    raw, normalized = sha256(frozen), lf_normalized_sha256(frozen)
    accepted = {raw} if sys.platform == "linux" else {raw, normalized}
    if match.group(1) not in accepted:
        raise RuntimeError(f"D07 agent_trace frozen companion hash mismatch: raw={raw} lf={normalized} expected={match.group(1)}")
    return {"agent_trace": str(agent), "agent_trace_sha256": sha256(agent), "frozen_companion_raw_sha256": raw,
            "frozen_companion_lf_sha256": normalized,
            "route_analyze": str(analyzer), "route_analyze_sha256": sha256(analyzer)}


def require_closed_round(rid: str, verdict: str) -> Path:
    """Read only the registered closure metadata, never prior raw payloads."""
    if not rid or Path(rid).name != rid:
        raise RuntimeError("closed round id is unsafe")
    directory, pin = ROUNDS / rid, ROOT / "runs/plan_batches/closed_round_pins" / f"{rid}.json"
    round_json, manifest = directory / "round.json", directory / "MANIFEST.sha256"
    for path in (directory, pin, round_json, manifest):
        if path.is_symlink() or not path.exists():
            raise RuntimeError(f"{rid} closed-round registration is incomplete")
    if not directory.is_dir() or not pin.is_file() or not round_json.is_file() or not manifest.is_file():
        raise RuntimeError(f"{rid} closed-round registration types differ")
    try:
        registered, document = json.loads(pin.read_text(encoding="utf-8")), json.loads(round_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{rid} closed-round metadata is unreadable") from exc
    primary, canonical = registered.get("round_sha256"), registered.get("round_json_sha256")
    actual_round = sha256(round_json)
    if (primary is not None and (not isinstance(primary, str) or len(primary) != 64)):
        raise RuntimeError(f"{rid} registered round_sha256 is malformed")
    if (canonical is not None and (not isinstance(canonical, str) or len(canonical) != 64)):
        raise RuntimeError(f"{rid} registered round_json_sha256 is malformed")
    if (primary is not None and canonical is not None and primary != canonical):
        raise RuntimeError(f"{rid} registered round SHA aliases differ")
    declared_round = canonical if canonical is not None else primary
    if (registered.get("rid") != rid or declared_round != actual_round
            or registered.get("manifest_sha256") != sha256(manifest)):
        raise RuntimeError(f"{rid} registered closed-round SHA differs")
    if pin.stat().st_mode & 0o222:
        raise RuntimeError(f"{rid} closed-round pin is writable")
    if document.get("round_id") != rid or document.get("verdict") != verdict:
        raise RuntimeError(f"{rid} formal D04 verdict is not {verdict}")
    # Deliberately metadata-only: rglob/stat never opens measurement payloads.
    for path in (directory, *directory.rglob("*")):
        if path.is_symlink() or path.stat().st_mode & 0o222:
            raise RuntimeError(f"{rid} sealed tree has writable or symlinked member: {path.name}")
    # Exact R045 predecessors may omit ``history_checker_*`` bindings. These
    # registered closures use only this capsule's byte-pinned canonical copy,
    # never through a mutable repository-level fallback or a round-local file.
    if (rid, verdict) in (('E2-R040a', 'failed_harness'), ('E2-R040c', 'failed_harness'), ('E2-R040d', 'failed_harness'), ('E2-R055b-gate-D06', 'failed_harness'), ('E2-R040f', 'measured')):
        checker = Path(__file__).resolve().with_name('r045_round_json_append_v1.py')
        if (checker.is_symlink() or not checker.is_file() or checker.stat().st_mode & 0o222
                or sha256(checker) != ROUND_WRITER_SHA):
            raise RuntimeError(f"{rid} sealed same-directory history checker differs")
    else:
        checker = directory / "round_json_append.py"
        # Failed R040/R046 did not archive this tool. Reuse the registered,
        # already sealed canonical writer rather than adding a tool to a failed round.
        if not checker.exists() and rid in (T20_RID, 'E2-R046') and verdict == 'failed_harness':
            registered_path = registered.get('history_checker_path')
            if not isinstance(registered_path, str) or not Path(registered_path).is_absolute():
                raise RuntimeError(f"{rid} external history checker binding is absent")
            checker = Path(registered_path)
            if (checker.is_symlink() or not checker.is_file() or checker.stat().st_mode & 0o222
                    or any(parent.is_symlink() for parent in checker.parents)
                    or registered.get('history_checker_sha256') != ROUND_WRITER_SHA
                    or sha256(checker) != ROUND_WRITER_SHA):
                raise RuntimeError(f"{rid} external history checker binding differs")
        if checker.is_symlink() or not checker.is_file():
            raise RuntimeError(f"{rid} pinned round-json checker is absent")
    checked = subprocess.run([str(VENV / "bin/python"), str(checker), str(directory), "check"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if checked.returncode:
        raise RuntimeError(f"{rid} D04 history check failed")
    return round_json


def require_r041_kept(root: Path) -> Path:
    return require_closed_round("E2-R041-gate-D17", "kept")


def require_t20_kept() -> Path:
    return require_closed_round(T20_RID, "kept")


def require_t20_failed_harness() -> Path:
    """HANDOFF section six permits continuing after failed-only D04 closure."""
    return require_closed_round(T20_RID, "failed_harness")


def process_birth(pid: int | None = None) -> dict:
    pid = os.getpid() if pid is None else pid
    fields = (Path("/proc") / str(pid) / "stat").read_text().rpartition(") ")[2].split()
    ticks = int(fields[19])
    if ticks <= 0:
        raise RuntimeError("D07 owner birth identity is invalid")
    return {"pid": pid, "start_ticks": ticks, "execution_id": f"{pid}:{ticks}"}


def argv_sha256(argv: list[str]) -> str:
    return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()


def child_argv(batch: int, receipt: Path, worktree: Path, output_root: Path) -> list[str]:
    return [str(VENV / "bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child", "--batch", str(batch),
            "--launch-receipt", str(receipt), "--worktree", str(worktree), "--output-root", str(output_root)]


def publish_child_binding(receipt_path: Path, receipt: dict, child: dict, *, lifecycle=None) -> dict:
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt.get("state") != "launched":
        raise RuntimeError("D07 launch receipt is not publishable")
    current = receipt_path.read_bytes(); identity = receipt_path.stat()
    if json.loads(current) != receipt:
        raise RuntimeError("D07 launch receipt changed before child binding")
    value = {**receipt, "child": child}
    if lifecycle is None or not callable(getattr(lifecycle, "publish_receipt", None)):
        raise RuntimeError("D07 owned lifecycle lacks atomic receipt publisher")
    lifecycle.publish_receipt(receipt_path, (identity.st_dev, identity.st_ino), value)
    return value


def require_child_receipt(receipt_path: Path, batch: int, worktree: Path, output_root: Path, *, rid: str | None = None,
                          expected_argv: list[str] | None = None, schema: str | None = None) -> dict:
    rid, schema = RID if rid is None else rid, "ft_d07_owned_launch/v2" if schema is None else schema
    expected = child_argv(batch, receipt_path, worktree, output_root) if expected_argv is None else expected_argv
    deadline = time.monotonic() + 30
    mine = process_birth()
    while time.monotonic() < deadline:
        if receipt_path.is_file() and not receipt_path.is_symlink():
            try: receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): receipt = {}
            child = receipt.get("child", {})
            if receipt.get("state") == "launched" and child == mine:
                if (receipt.get("schema") != schema or receipt.get("rid") != rid or receipt.get("batch") != batch or receipt.get("batch_pid") != mine["pid"] or receipt.get("candidate_commit") != CANDIDATE
                        or receipt.get("argv_sha256") != argv_sha256(expected)):
                    raise RuntimeError("D07 child launch receipt binding differs")
                return receipt
        time.sleep(.05)
    raise RuntimeError("D07 child lacks its controller-bound launch receipt")


def take_d07_gpu_lock(rid: str, batch: int) -> dict:
    """D07's narrow use of the existing O_EXCL owner-lock convention."""
    identity = process_birth()
    token = {"owner": rid, "batch": batch, **identity}
    encoded = json.dumps(token, sort_keys=True)
    try:
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("foreign GPU lock exists; D07 must remain queued") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush(); os.fsync(handle.fileno())
    stat = LOCK.stat()
    return {**token, "lock_inode": stat.st_ino, "lock_device": stat.st_dev, "lock_token": encoded}


def release_d07_gpu_lock(owner: dict) -> None:
    if not LOCK.exists() or LOCK.is_symlink():
        raise RuntimeError("D07 owner lock disappeared before release")
    stat = LOCK.stat()
    if (stat.st_ino, stat.st_dev) != (owner["lock_inode"], owner["lock_device"]) or LOCK.read_text(encoding="utf-8") != owner["lock_token"]:
        raise RuntimeError("D07 refuses to release a foreign/replaced GPU lock")
    LOCK.unlink()


def require_gpu_idle() -> list[int]:
    rows = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True).splitlines()
    values = [int(row) for row in rows if row.strip()]
    if not values or any(value >= 1000 for value in values):
        raise RuntimeError(f"GPU is not idle for D07: {values}")
    return values


def load_owned_lifecycle(source: Path = OWNED_SOURCE):
    protocol = source / "t17_owned_launch_protocol.py"
    if protocol.is_symlink() or sha256(protocol) != OWNED_PROTOCOL_SHA:
        raise RuntimeError("pinned owned lifecycle source differs")
    spec = importlib.util.spec_from_file_location("d07_owned_lifecycle", protocol)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # The pinned legacy protocol has group cleanup, but no birth reader.
    # Supply the exact /proc identity required by these newer callers.
    module.process_identity = process_identity
    return module


def process_identity(pid: int) -> dict | None:
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rpartition(') ')[2].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    ticks = int(fields[19])
    if ticks <= 0:
        raise RuntimeError('owned process birth is invalid')
    return {'pid': pid, 'start_ticks': ticks, 'execution_id': f'{pid}:{ticks}',
            'pgid': int(fields[2]), 'session': int(fields[3]), 'state': fields[0]}


def verify_frozen_cold_helpers(source: Path = OWNED_SOURCE) -> dict:
    helpers = source / "helpers"
    cold, probe = helpers / "raw/cold_eq.py", helpers / "raw/probe_ft_cold32k.py"
    if any(path.is_symlink() or not path.is_file() for path in (cold, probe)):
        raise RuntimeError("sealed D07 cold helper source is unavailable")
    if sha256(cold) != COLD_RAW_SHA or sha256(probe) != PROBE_RAW_SHA:
        raise RuntimeError("sealed D07 cold helper bytes differ")
    return {"cold_eq_raw": str(cold), "cold_eq_raw_sha256": COLD_RAW_SHA,
            "probe_raw": str(probe), "probe_raw_sha256": PROBE_RAW_SHA}


def clean_environment(worktree: Path, *, trace_dir: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("FT_") or key == "PYTHONPATH" or key == "CUDA_VISIBLE_DEVICES":
            env.pop(key)
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        PYTHONPATH=str(worktree / "python"),
        VIRTUAL_ENV=str(VENV),
        PATH=str(VENV / "bin") + ":" + env.get("PATH", ""),
        CUDA_VISIBLE_DEVICES="0",
    )
    if trace_dir is not None:
        env["FT_DEV_ROUTE_TRACE"] = str(trace_dir)
        env["FT_DEV_PAUSE_ENDPOINT"] = "1"
    return env


def serve_argv(port: int) -> list[str]:
    return [
        str(VENV / "bin/ft"), "serve", "--model-path", str(MODEL_PATH),
        "--served-model-name", MODEL, "--host", "127.0.0.1", "--port", str(port),
        "--memory-ratio", "0.88", "--moe-cache-auto", "--moe-prefill-hit-d2d",
        "--ple-backend", "pinned", "--moe-strategy", "offload",
        "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2",
        "--cuda-graph-max-bs", "2", "--kv-reserve-tokens", "49152",
        "--max-seq-len-override", "49152", "--max-prefill-length", "4096",
        "--enable-cache-report", "--enable-special-token-ckpt", "--tool-call-parser", "qwen3_coder",
        "--reasoning-parser", "qwen3", "--prefill-layer-major", "--mamba-host-slots", "0",
    ]


def start_server(directory: Path, worktree: Path, port: int, trace_dir: Path | None) -> subprocess.Popen:
    env = clean_environment(worktree, trace_dir=trace_dir)
    argv = serve_argv(port)
    (directory / "SERVE_CMD.txt").write_text(
        "env " + " ".join(f"{key}={shlex.quote(env[key])}" for key in sorted(env) if key in {"CUDA_VISIBLE_DEVICES", "FT_DEV_PAUSE_ENDPOINT", "FT_DEV_ROUTE_TRACE", "PYTHONPATH", "VIRTUAL_ENV"})
        + " " + shlex.join(argv) + "\n", encoding="utf-8"
    )
    log = (directory / "serve.log").open("x", encoding="utf-8")
    process = subprocess.Popen(argv, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        birth = load_owned_lifecycle().process_identity(process.pid)
        if birth is None or birth.get("pgid") != process.pid or birth.get("session") != process.pid:
            raise RuntimeError("D07 owned service lacks a private process group/session")
        write_new(directory / "owned_process.json", {"pid": process.pid, "pgid": process.pid, "port": port, "birth": birth})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"D07 owned service exited during startup: {process.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    health = json.load(response)
                if health.get("status") == "ok":
                    write_new(directory / "health.json", health)
                    return process
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise TimeoutError("D07 owned service did not become healthy")
    except BaseException:
        # The shared lifecycle checks the whole PGID, including descendants.
        try:
            load_owned_lifecycle().stop_owned_process(process)
        except BaseException as cleanup_error:
            cleanup_error.owned_process = process
            cleanup_error.owned_cleanup_failed = True
            raise
        raise


def invoke_cold_eq(worktree: Path, port: int, cold_id: str, output: Path, helper_source: Path = OWNED_SOURCE) -> None:
    """Run the established cold_eq request unchanged except for its loopback URL.

    cold_eq has no URL argument.  This small adapter injects the candidate
    probe module with an ephemeral URL, then executes the candidate cold_eq.py
    source; request construction and stream handling remain that source.
    """
    verify_frozen_cold_helpers(helper_source)
    probe = helper_source / "helpers/raw/probe_ft_cold32k.py"
    cold = helper_source / "helpers/raw/cold_eq.py"
    spec = importlib.util.spec_from_file_location("probe_ft_cold32k", probe)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.URL = f"http://127.0.0.1:{port}/v1/chat/completions"
    old_module, old_argv = sys.modules.get("probe_ft_cold32k"), sys.argv[:]
    sys.modules["probe_ft_cold32k"] = module
    sys.argv = [str(cold), cold_id, str(output), "32052", "128"]
    try:
        runpy.run_path(str(cold), run_name="__main__")
    finally:
        sys.argv = old_argv
        if old_module is None:
            del sys.modules["probe_ft_cold32k"]
        else:
            sys.modules["probe_ft_cold32k"] = old_module


def g3_compare(off_json: Path, on_json: Path) -> dict:
    off, on = json.loads(off_json.read_text(encoding="utf-8")), json.loads(on_json.read_text(encoding="utf-8"))
    for name, row in (("off", off), ("on", on)):
        record = row.get("record")
        if not isinstance(record, dict) or not isinstance(row.get("text"), str) or not row["text"]:
            raise RuntimeError(f"G3 failed: {name} cold_eq response is incomplete")
        if record.get("cold_id") is None or record.get("finish_reason") not in {"stop", "length"}:
            raise RuntimeError(f"G3 failed: {name} cold_eq request/response binding is incomplete")
        if record.get("built_tokens") != 32052 or record.get("completion_tokens") is None:
            raise RuntimeError(f"G3 failed: {name} cold_eq request shape differs")
    if off["record"]["cold_id"] != on["record"]["cold_id"]:
        raise RuntimeError("G3 failed: cold_eq IDs differ")
    if off["text"] != on["text"]:
        raise RuntimeError("G3 failed: same cold_eq request text differs with FT_DEV_ROUTE_TRACE enabled")
    return {"same_cold_id": True,
            "text_utf8_sha256": hashlib.sha256(off["text"].encode("utf-8")).hexdigest(), "byte_identical": True}


def invoke_agent_trace(worktree: Path, port: int, output: Path) -> None:
    command = [str(VENV / "bin/python"), str(worktree / "scripts/agent_trace.py"), "generate", "--route-evidence",
               "--base-url", f"http://127.0.0.1:{port}/v1", "--model", MODEL, "--rounds", "2", "--max-tokens", "128", "--out", str(output)]
    subprocess.run(command, cwd=worktree, env=clean_environment(worktree), check=True)


def invoke_analyzer(worktree: Path, route_dir: Path, trace: Path, serve_log: Path, summary: Path) -> None:
    subprocess.run([str(VENV / "bin/python"), str(worktree / "scripts/route_analyze.py"), str(route_dir), "--traces", str(trace),
                    "--serve-log", str(serve_log), "--out", str(summary)], cwd=worktree, env=clean_environment(worktree), check=True)
    report = json.loads(summary.read_text(encoding="utf-8"))
    if not report.get("suffix_tokens") or not report.get("business_uids"):
        raise RuntimeError("G4 failed: analyzer lacks UID-bound real response suffix evidence")


def prepared_packet(worktree: Path, helper_source: Path = OWNED_SOURCE) -> dict:
    port = dynamic_fixture_port()
    return {"schema": "ft_d07_g3g4_prepare/v1", "rid": RID, "candidate_commit": CANDIDATE,
            "candidate": checked_worktree(worktree), "candidate_tools": verify_d07_tools(worktree), "cold_helpers": verify_frozen_cold_helpers(helper_source), "output_root": str(RUNS), "fixture_port": port,
            "cuda_visible_devices_cpu_guard": "", "run_requires": ["explicit --run", "Linux host", "R041 D04 kept", "T20 E2-R040 D04 kept", "atomic D07 O_EXCL lock", "GPU idle gate"],
            "g3": "same cold_eq.py request, FT_DEV_ROUTE_TRACE off/on, UTF-8 text byte equality",
            "g4": "route_analyze requires route/serve-log per-UID #route-reqs totals plus ACK UID/actual completion binding",
            "timing": "not a performance measurement; trace mode must log CUDA graph disabled"}


def execute(worktree: Path, output_root: Path, *, owned_child: bool = False, batch: int | None = None, launch_receipt: Path | None = None) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("D07 --run requires the Linux GPU host")
    if not owned_child:
        r041, t20 = require_r041_kept(ROOT), require_t20_kept()
        packet = prepared_packet(worktree)
        owned = load_owned_lifecycle(); helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", ATOMIC_HELPER_SHA, "d07_atomic_launcher")
        if LOCK.exists() or LOCK.is_symlink(): raise RuntimeError("foreign GPU lock exists; D07 remains queued")
        batch = helper.next_batch(ROUNDS); RUNS.mkdir(parents=True, exist_ok=True); receipt_path = RUNS / f"launch_{RID}_batch{batch}.json"
        argv = child_argv(batch, receipt_path, worktree, output_root)
        reserved = {"schema":"ft_d07_owned_launch/v2","state":"reserved","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,
                    "argv_sha256":argv_sha256(argv),"owned_protocol_sha256":OWNED_PROTOCOL_SHA,"atomic_helper_sha256":ATOMIC_HELPER_SHA,
                    "controller":process_birth(),"prerequisites":{"E2-R041-gate-D17":sha256(r041),T20_RID:sha256(t20)},"packet_sha256":hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()}
        receipt = owned.reserve_process(helper,batch,RID,argv,receipt_path,reserved)
        identity = owned.process_identity(receipt["batch_pid"])
        if identity is None or identity.get("pid") != receipt["batch_pid"] or type(identity.get("start_ticks")) is not int:
            raise RuntimeError("D07 reserved child birth is unavailable")
        return publish_child_binding(receipt_path,receipt,{"pid":identity["pid"],"start_ticks":identity["start_ticks"],"execution_id":f"{identity['pid']}:{identity['start_ticks']}"},lifecycle=owned)
    if batch is None or launch_receipt is None:
        raise RuntimeError("D07 owned child requires controller receipt and reserved batch")
    require_child_receipt(launch_receipt,batch,worktree,output_root)
    r041, t20 = require_r041_kept(ROOT), require_t20_kept()
    packet = prepared_packet(worktree)
    owner = take_d07_gpu_lock(RID, batch)
    run_dir = None
    process = None
    try:
        idle = require_gpu_idle()
        run_dir = output_root / (RID + "_" + time.strftime("%Y%m%d_%H%M%S"))
        run_dir.mkdir(parents=True)
        shutil.copy2(__file__, run_dir / Path(__file__).name)
        write_new(run_dir / "preflight.json", {**packet, "r041_closure": str(r041), "r041_closure_sha256": sha256(r041), "t20_closure": str(t20), "t20_closure_sha256": sha256(t20), "gpu_owner": owner, "gpu_memory_mib": idle, "development_selfcheck_not_acceptance": True})
        cold_id = RID + "-cold"
        off_dir, on_dir = run_dir / "g3_off", run_dir / "g3_on"
        off_dir.mkdir(); on_dir.mkdir()
        off_port = dynamic_fixture_port(); process = None
        try:
            process = start_server(off_dir, worktree, off_port, None)
            invoke_cold_eq(worktree, off_port, cold_id, off_dir / "cold.json")
        finally:
            if process is not None:
                load_owned_lifecycle().stop_owned_process(process)
        route_dir = on_dir / "routes"; route_dir.mkdir()
        on_port = dynamic_fixture_port(); process = None
        try:
            process = start_server(on_dir, worktree, on_port, route_dir)
            invoke_cold_eq(worktree, on_port, cold_id, on_dir / "cold.json")
            trace = on_dir / "trace.json"
            invoke_agent_trace(worktree, on_port, trace)
        finally:
            if process is not None:
                load_owned_lifecycle().stop_owned_process(process)
        log = on_dir / "serve.log"
        text = log.read_text(encoding="utf-8", errors="replace")
        if "CUDA graph disabled for development route trace" not in text:
            raise RuntimeError("trace mode did not leave the required CUDA graph disabled marker in serve.log")
        summary = on_dir / "summary.json"
        invoke_analyzer(worktree, route_dir, trace, log, summary)
        summary_doc = json.loads(summary.read_text(encoding="utf-8"))
        result = {"schema": "ft_d07_g3g4_result/v1", "verdict": "development_selfcheck_pass", "rid": RID, "batch": batch, "gpu_owner": owner, "candidate_commit": CANDIDATE,
              "development_selfcheck_not_acceptance": True, "g3": g3_compare(off_dir / "cold.json", on_dir / "cold.json"),
              "g4": {"summary": str(summary), "summary_sha256": sha256(summary), "uid_bound": bool(summary_doc.get("suffix_tokens") and summary_doc.get("business_uids")), "suffix_tokens": len(summary_doc["suffix_tokens"])}, "cuda_graph_disabled_marker": True,
              "timing": "intentionally excluded: trace mode disables CUDA graph", "run_dir": str(run_dir)}
        write_new(run_dir / "result.json", result)
        return result
    except BaseException as exc:
        process = getattr(exc, "owned_process", process)
        if run_dir is not None:
            write_new(run_dir / "failed_harness.json", {"rid": RID, "batch": batch, "gpu_owner": owner, "error": repr(exc), "development_selfcheck_not_acceptance": True})
        raise
    finally:
        if process is not None and load_owned_lifecycle().owned_group_alive(process.pid):
            raise RuntimeError("D07 owned service remains; preserve GPU lock for recovery")
        release_d07_gpu_lock(owner)
        if run_dir is not None:
            write_new(run_dir / "owned_cleanup.json", {"schema": "ft_d07_owned_cleanup/v1", "rid": RID,
                      "batch": batch, "candidate_commit": CANDIDATE, "gpu_owner": owner, "lock_released": True})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="start the queued GPU self-check; omitted is CPU preparation only")
    parser.add_argument("--owned-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--batch", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--launch-receipt", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worktree", type=Path, default=WORKTREE)
    parser.add_argument("--output-root", type=Path, default=RUNS)
    args = parser.parse_args(argv)
    if not args.run:
        print(json.dumps(prepared_packet(args.worktree), ensure_ascii=False, sort_keys=True))
        return 0
    print(json.dumps(execute(args.worktree, args.output_root, owned_child=args.owned_child, batch=args.batch, launch_receipt=args.launch_receipt), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
