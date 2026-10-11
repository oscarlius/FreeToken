#!/usr/bin/env python3
"""D16 API-only interleave6 executor.  ``--filedry`` never launches anything."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = Path("/data2/FreeToken")
WT = ROOT / "wt/e2base1-p1"
VENV = ROOT / "venv"
EVAL = ROOT / "evaluation/d16_api"
RUNS = ROOT / "runs/dev_D16/r040i_api_d16"
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
RID = "E2-R040i-api-D16"
CANDIDATE = "effb9969706922ddad9e59b96377e46469ebe97f"
D07 = ROOT / "runs/dev_T16/r063_default_gate_v1/d07_g3g4_prepare.py"
PAIR = ROOT / "runs/dev_D16/r040h_v1_cpu_20261008_1610/runtime/ft_batch_port_pair_v1.py"
D07_SHA = "c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0"
PAIR_SHA = "415c1255ebbba81027c4526acd377f68f87889e31bfb4a58b79053c8abb73a34"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as out: json.dump(value, out, ensure_ascii=False, sort_keys=True, indent=2); out.write("\n")
def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None; spec.loader.exec_module(module); return module


def checked_inputs() -> dict:
    names = ("scope_payloads.json", "interleave_input_binding.json", "request_schema.json", "sdk_completions.py", "live_scope.py")
    paths = {name: EVAL / name for name in names}
    if any(path.is_symlink() or not path.is_file() for path in paths.values()): raise RuntimeError("D16 API input closure unavailable")
    scope = json.loads(paths["scope_payloads.json"].read_text())
    binding = json.loads(paths["interleave_input_binding.json"].read_text())
    if scope.get("services") != 6 or len(scope.get("calls", [])) != 8 or len(binding.get("inputs", [])) != 2: raise RuntimeError("D16 API scope differs")
    if any(row.get("service") not in {f"interleave_{n}" for n in range(6)} for row in scope["calls"]): raise RuntimeError("D16 non-interleave service")
    if not all(row.get("retokenized_matches_original") is True for row in binding["inputs"]): raise RuntimeError("D16 text mapping not CPU round-trip")
    return {name: sha(path) for name, path in paths.items()}


def candidate() -> dict:
    if WT.is_symlink() or sha(D07) != D07_SHA or sha(PAIR) != PAIR_SHA: raise RuntimeError("pinned lifecycle or port helper differs")
    head = subprocess.check_output(["git", "-C", str(WT), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(WT), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != CANDIDATE or dirty: raise RuntimeError("R040i requires clean effb996 candidate")
    return {"worktree": str(WT), "commit": head, "tracked_clean": True}


def argv(port: int) -> list[str]:
    d07 = load(D07, "r040i_d07")
    base = d07.serve_argv(port)
    replace = {"--max-running-requests": "4", "--cuda-graph-max-bs": "4", "--kv-reserve-tokens": "98304", "--max-seq-len-override": "98304"}
    for flag, value in replace.items(): base[base.index(flag) + 1] = value
    forbidden = ("FT_D16_CACHE_INIT", "FT_D16_EXECUTION_ID", "FT_D16_SERVICE_CAPTURE_", "FT_DEV_STATE_DUMP", "FT_T17_")
    if any(key.startswith(forbidden) for key in os.environ) or any(item.startswith("--max-running-requests") for item in []): raise RuntimeError("native D16 capture environment is forbidden")
    return ["numactl", "--cpunodebind=0,1", "--interleave=all", *base]


def packet() -> dict:
    pair = load(PAIR, "r040i_pair")
    port = pair.dynamic_port()
    command = argv(port)
    required = {"--memory-ratio": "0.88", "--max-running-requests": "4", "--cuda-graph-max-bs": "4", "--kv-reserve-tokens": "98304", "--max-seq-len-override": "98304"}
    for flag, value in required.items():
        if command[command.index(flag) + 1] != value: raise RuntimeError("final D16 serve argv differs")
    return {"schema": "ft_r040i_api_d16_prepare/v1", "rid": RID, "candidate": candidate(), "input_sha256": checked_inputs(),
            "port_pair": pair.port_receipt(port), "serve_argv": command, "serve_argv_sha256": sha256_argv(command),
            "scope": "interleave6_services_8_calls_only", "warm": "deferred_no_actual_hit_evidence",
            "limits": ["SDK API behavior equivalence only", "text mapping is not worker token-input proof", "API overlap is not physical batching", "no native collector/cache/watchdog"]}


def sha256_argv(value: list[str]) -> str: return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def start(d07, directory: Path, port: int) -> subprocess.Popen:
    env = d07.clean_environment(WT); env["CUDA_VISIBLE_DEVICES"] = "0"
    command = argv(port); selected = {key: env[key] for key in ("CUDA_VISIBLE_DEVICES", "PYTHONPATH", "VIRTUAL_ENV")}
    write(directory / "service_environment.json", {"selected": selected, "native_capture_keys": [], "clean_environment": True})
    (directory / "SERVE_CMD.txt").write_text("env " + shlex.join([f"{key}={value}" for key, value in selected.items()]) + " " + shlex.join(command) + "\n", encoding="utf-8")
    log = (directory / "serve.log").open("x", encoding="utf-8")
    process = subprocess.Popen(command, cwd=WT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    birth = d07.load_owned_lifecycle().process_identity(process.pid)
    if birth is None or birth.get("pgid") != process.pid or birth.get("session") != process.pid: raise RuntimeError("owned server identity differs")
    write(directory / "owned_process.json", {"birth": birth, "port": port})
    for _ in range(450):
        if process.poll() is not None: raise RuntimeError(f"service exited: {process.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response: health = json.load(response)
            if health.get("status") == "ok": write(directory / "health.json", health); return process
        except (OSError, ValueError): time.sleep(2)
    raise TimeoutError("D16 API service did not become healthy")


def compare(run_dir: Path) -> None:
    scope = json.loads((EVAL / "scope_payloads.json").read_text())
    rows = {}
    for item in scope["calls"]:
        name = "single.json" if item["label"] == "single" else f"{item['label']}.json"
        rows[item["compare"]] = rows.get(item["compare"], []) + [json.loads((run_dir / item["service"] / "calls" / name).read_text())["projection"]]
    module = load(EVAL / "sdk_completions.py", "r040i_sdk")
    if any(len(values) != 2 for values in rows.values()): raise RuntimeError("D16 pair results incomplete")
    for values in rows.values(): module.compare_completion(*values)
    write(run_dir / "comparison.json", {"schema": "ft_d16_api_comparison/v1", "pairs": sorted(rows), "text_finish_usage_equal": True})


def child_argv(batch: int, receipt: Path) -> list[str]:
    return [str(VENV / "bin/python"), str(Path(__file__).resolve()), "--owned-child", "--batch", str(batch), "--launch-receipt", str(receipt)]


def require_receipt(d07, receipt_path: Path, batch: int) -> dict:
    expected = child_argv(batch, receipt_path)
    doc = json.loads(receipt_path.read_text())
    identity = d07.process_identity(os.getpid())
    if (doc.get("state") != "launched" or doc.get("schema") != "ft_r040i_api_owned_launch/v1" or doc.get("rid") != RID
            or doc.get("batch") != batch or doc.get("candidate_commit") != CANDIDATE or doc.get("argv_sha256") != sha256_argv(expected)
            or doc.get("child") != identity):
        raise RuntimeError("R040i owned-child receipt binding differs")
    return doc


def execute_owned(batch: int, receipt_path: Path) -> dict:
    if sys.platform != "linux": raise RuntimeError("R040i --run requires Linux GPU host")
    d07, package = load(D07, "r040i_d07"), packet(); require_receipt(d07, receipt_path, batch)
    owner = d07.take_d07_gpu_lock(RID, -1); process = None; run_dir = RUNS / f"{RID}_{time.strftime('%Y%m%d_%H%M%S')}"
    try:
        d07.require_gpu_idle(); run_dir.mkdir(parents=True); write(run_dir / "preflight.json", package)
        for service in (f"interleave_{n}" for n in range(6)):
            directory = run_dir / service; directory.mkdir(); port = load(PAIR, "pair").dynamic_port(); process = start(d07, directory, port)
            try: subprocess.run([str(ROOT / "evaluation/toolchain/venv-eval/bin/python"), str(EVAL / "live_scope.py"), "--base-url", f"http://127.0.0.1:{port}", "--model", "Qwen3.8-Flash-Next-NVFP4", "--service", service, "--output", str(directory / "calls")], check=True, cwd=EVAL, env={**os.environ, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
            finally: d07.load_owned_lifecycle().stop_owned_process(process); process = None
        compare(run_dir); write(run_dir / "result.json", {"verdict": "SDK_API_behavior_equivalence_pass", "not_formal_D04_seal": True}); return {"run_dir": str(run_dir)}
    finally:
        if process is not None and d07.load_owned_lifecycle().owned_group_alive(process.pid): raise RuntimeError("owned service remains")
        d07.release_d07_gpu_lock(owner)


def launch_owned() -> dict:
    """Controller branch: reserve a single owned child before it can touch GPU state."""
    if sys.platform != "linux": raise RuntimeError("R040i --run requires Linux GPU host")
    d07, package = load(D07, "r040i_d07"), packet(); owned = d07.load_owned_lifecycle()
    helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", d07.ATOMIC_HELPER_SHA, "r040i_atomic_launcher")
    if (ROUNDS / RID).exists() or d07.LOCK.exists() or d07.LOCK.is_symlink(): raise RuntimeError("R040i formal RID or GPU lock already exists")
    batch = helper.next_batch(ROUNDS); RUNS.mkdir(parents=True, exist_ok=True); receipt_path = RUNS / f"launch_{RID}_batch{batch}.json"
    command = child_argv(batch, receipt_path)
    reserved = {"schema": "ft_r040i_api_owned_launch/v1", "state": "reserved", "rid": RID, "batch": batch,
                "candidate_commit": CANDIDATE, "argv_sha256": sha256_argv(command), "controller": d07.process_birth(),
                "packet_sha256": hashlib.sha256(json.dumps(package, sort_keys=True).encode()).hexdigest(),
                "lifecycle_source_sha256": D07_SHA, "atomic_helper_sha256": d07.ATOMIC_HELPER_SHA}
    receipt = owned.reserve_process(helper, batch, RID, command, receipt_path, reserved)
    child = d07.process_identity(receipt["batch_pid"])
    if child is None: raise RuntimeError("R040i child birth is unavailable")
    current, identity = receipt_path.read_bytes(), receipt_path.stat()
    if json.loads(current) != receipt: raise RuntimeError("R040i launch receipt changed before child bind")
    owned.publish_receipt(receipt_path, (identity.st_dev, identity.st_ino), {**receipt, "child": child})
    return {"launch_receipt": str(receipt_path), "batch": batch, "child": child}


def main(argv_: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--filedry", action="store_true"); parser.add_argument("--run", action="store_true"); parser.add_argument("--owned-child", action="store_true", help=argparse.SUPPRESS); parser.add_argument("--batch", type=int, help=argparse.SUPPRESS); parser.add_argument("--launch-receipt", type=Path, help=argparse.SUPPRESS); args = parser.parse_args(argv_)
    if args.owned_child:
        if not args.run or args.filedry or args.batch is None or args.launch_receipt is None: parser.error("owned child requires --run, batch and receipt")
        print(json.dumps(execute_owned(args.batch, args.launch_receipt), ensure_ascii=False, sort_keys=True)); return 0
    if args.filedry == args.run: parser.error("choose exactly one of --filedry or --run")
    if args.filedry: print(json.dumps({**packet(), "filedry": True, "no_rid_batch_lock_popen_or_request": True}, ensure_ascii=False, sort_keys=True))
    else: print(json.dumps(launch_owned(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
