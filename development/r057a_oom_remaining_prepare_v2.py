#!/usr/bin/env python3
"""E2-R057 four-arm OOM diagnostic preparation and FILEDRY only.

GPU launch, HTTP requests, locks, batch allocation, and formal RID creation are
owned by the round controller and intentionally absent here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RID = "E2-R057a"
COLD_ID = "E2-R057"
EXPECTED_INPUT_SHA = "cd003af3d6f2713fbcf896fe756fb3baf79e38100f10ae5eb4bdcbc937710632"
CANDIDATE = "effb9969706922ddad9e59b96377e46469ebe97f"
ROOT = Path("/data2/FreeToken")
WT = ROOT / "wt/e2base1-p1"
VENV = ROOT / "venv"
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
HERE = Path(__file__).resolve().parent
PORT_SOURCE = HERE / "ft_batch_port_pair_v1.py"
from ft_batch_port_pair_v1 import dynamic_port, port_receipt
D07_SOURCE = Path(os.environ.get("R057_D07_SOURCE", HERE / "d07_g3g4_prepare.py"))
FILE_PREP_SOURCE = Path(os.environ.get("R057_FILE_PREP_SOURCE", HERE / "d07_r046a_file_prepare_v1.py"))
WRAPPER_SOURCE = HERE / "r057_memory_history_startup.py"
WINDOW = 98304
MEMORY_RATIO = "0.88"
PROMPT_TOKENS = 32064

ARMS = (
    {"name": "A_trace_on_pause_off", "trace": True, "pause": False, "cuda_graph_max_bs": 2,
     "compare_to": "C_trace_on_pause_on", "single_variable": "pause"},
    {"name": "B_trace_off_pause_on", "trace": False, "pause": True, "cuda_graph_max_bs": 2,
     "compare_to": "C_trace_on_pause_on", "single_variable": "trace"},
    {"name": "C_trace_on_pause_on", "trace": True, "pause": True, "cuda_graph_max_bs": 2,
     "compare_to": None, "single_variable": None},
    {"name": "D_trace_off_pause_off_graph_off", "trace": False, "pause": False, "cuda_graph_max_bs": 0,
     "compare_to": "default_graph_on_no_switches", "single_variable": "cuda_graph_max_bs"},
)
ARMS = ARMS[2:]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def load_d07():
    if D07_SOURCE.is_symlink() or not D07_SOURCE.is_file():
        raise RuntimeError("R057 requires the shared D07 source")
    spec = importlib.util.spec_from_file_location("r057_d07", D07_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    module.CANDIDATE = CANDIDATE
    module.WORKTREE = WT
    module.RID = RID
    return module


def load_file_prep():
    if FILE_PREP_SOURCE.is_symlink() or not FILE_PREP_SOURCE.is_file():
        raise RuntimeError("R057 requires the shared file-preparation source")
    spec = importlib.util.spec_from_file_location("r057_file_prep", FILE_PREP_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def require_cuda_graph_flag() -> None:
    args_source = WT / "python" / "freetoken" / "server" / "args.py"
    if args_source.is_symlink() or not args_source.is_file() or "--cuda-graph-max-bs" not in args_source.read_text(encoding="utf-8"):
        raise RuntimeError("candidate ServerArgs lacks --cuda-graph-max-bs; do not substitute a guessed flag")


def _replace(argv: list[str], flag: str, value: str) -> None:
    if flag not in argv:
        raise RuntimeError(f"shared D07 argv lacks {flag}")
    argv[argv.index(flag) + 1] = value


def arm_plan(arm: dict, port: int, root: Path) -> dict:
    d07 = load_d07()
    env = d07.clean_environment(WT, trace_dir=None)
    env.pop("FT_DEV_ROUTE_TRACE", None)
    env.pop("FT_DEV_PAUSE_ENDPOINT", None)
    if arm["trace"]:
        env["FT_DEV_ROUTE_TRACE"] = str(root / arm["name"] / "route")
    if arm["pause"]:
        env["FT_DEV_PAUSE_ENDPOINT"] = "1"
    argv = list(d07.serve_argv(port))
    _replace(argv, "--memory-ratio", MEMORY_RATIO)
    _replace(argv, "--kv-reserve-tokens", str(WINDOW))
    _replace(argv, "--max-seq-len-override", str(WINDOW))
    _replace(argv, "--cuda-graph-max-bs", str(arm["cuda_graph_max_bs"]))
    wrapper = root / arm["name"] / "r057_memory_history_startup.py"
    command = [str(VENV / "bin/python"), str(wrapper), "--snapshot-dir", str(root / arm["name"] / "memory_history"), "--", *argv[1:]]
    return {"arm": arm["name"], "port": port, "port_pair": port_receipt(port), "environment": {key: env[key] for key in sorted(env) if key in {"CUDA_VISIBLE_DEVICES", "FT_DEV_ROUTE_TRACE", "FT_DEV_PAUSE_ENDPOINT", "PYTHONPATH", "VIRTUAL_ENV"}}, "ft_argv": argv, "startup_argv": command,
            "cold_prompt_tokens": PROMPT_TOKENS, "record_memory_history": True,
            "snapshot_policy": "model load, request completion, model-load error, process exit; request OOM is captured by process-exit/error snapshot", "compare_to": arm["compare_to"], "single_variable": arm["single_variable"]}


def serve_args_diff(arm: dict) -> dict:
    base = {"trace": False, "pause": False, "cuda_graph_max_bs": 2, "memory_ratio": MEMORY_RATIO, "kv_reserve_tokens": WINDOW, "max_seq_len_override": WINDOW}
    actual = {"trace": arm["trace"], "pause": arm["pause"], "cuda_graph_max_bs": arm["cuda_graph_max_bs"], "memory_ratio": MEMORY_RATIO, "kv_reserve_tokens": WINDOW, "max_seq_len_override": WINDOW}
    comparisons = {
        "A_trace_on_pause_off": {"pair": "A_vs_C", "single_variable": "pause", "this_arm": False, "C_trace_on_pause_on": True},
        "B_trace_off_pause_on": {"pair": "B_vs_C", "single_variable": "trace", "this_arm": False, "C_trace_on_pause_on": True},
        "C_trace_on_pause_on": {"role": "controlled_reference_for_A_and_B"},
        "D_trace_off_pause_off_graph_off": {"role": "graph_off_mechanism_reference_only", "not_a_controlled_R056_comparison": True},
    }
    return {"schema": "ft_r057_serve_args_diff/v1", "baseline": base, "actual": actual,
            "differences": {key: {"baseline": base[key], "actual": actual[key]} for key in base if base[key] != actual[key]},
            "controlled_comparison": comparisons[arm["name"]],
            "runtime_validation": {"required_after_start": True,
                                   "must_compare_parsed_server_args": True}}


def packet(output_root: Path = ROUNDS) -> dict:
    require_cuda_graph_flag()
    return {"schema": "ft_r057_oom_diagnostic_prepare/v1", "rid": RID, "candidate_commit": CANDIDATE,
            "worktree": str(WT), "window": WINDOW, "memory_ratio": MEMORY_RATIO, "cold_prompt_tokens": PROMPT_TOKENS,
            "diagnostic_only": True, "verdict": "pending_diagnostic", "preserved_round": "E2-R057", "cold_id": COLD_ID, "arms": [dict(arm) for arm in ARMS],
            "predecessor_admission": "Controller reads only predecessor round SHA, RO state, and D04 history.",
            "required_sources": {str(path): sha256(path) for path in (Path(__file__).resolve(), D07_SOURCE, FILE_PREP_SOURCE, WRAPPER_SOURCE, PORT_SOURCE)}}


def file_dry_run(output_root: Path = ROUNDS) -> dict:
    if os.name != "posix":
        raise RuntimeError("R057 FILEDRY requires Linux")
    require_cuda_graph_flag()
    target = output_root / f".dryrun_R057a_v2_{RID}"
    if target.exists():
        raise RuntimeError("R057 FILEDRY target already exists")
    target.mkdir(mode=0o700)
    plans = []
    try:
        d07 = load_d07()
        sources = archive_sources(target)
        for arm in ARMS:
            arm_dir = target / arm["name"]
            port = dynamic_port()
            plan = arm_plan(arm, port, target)
            _write_arm_files(d07, arm_dir, plan)
            write_new(arm_dir / "file_probe.json", {"schema": "ft_r057_file_probe/v1", "not_measurement": True,
                                                       "service_started": False, "requests_sent": False,
                                                       "snapshot_created": False, "purpose": "formal arm outputs"})
            for relative in ("memory_history/memory_samples.jsonl", "memory_history/snapshots.jsonl", "owned_process.json",
                             "health.json", "serve_args.txt", "cold.json", "arm_result.json", "owned_cleanup.json",
                             "error.json"):
                write_new(arm_dir / relative, {"schema": "ft_r057_file_probe/v1", "not_measurement": True,
                                                "purpose": "formal execution output"})
            snapshot_probe = arm_dir / "memory_history" / "FILEDRY_path_probe.pickle"
            snapshot_probe.write_bytes(pickle.dumps({"schema": "ft_r057_filedry_snapshot_path_probe/v1", "not_cuda_snapshot": True}, protocol=4))
            write_new(arm_dir / "memory_history" / "FILEDRY_path_probe.json", {"path": str(snapshot_probe), "sha256": sha256(snapshot_probe), "md5": hashlib.md5(snapshot_probe.read_bytes()).hexdigest(), "not_cuda_snapshot": True})
            plans.append(plan)
        for relative in ("runtime_sources/manifest.json", "preflight.json", "result.json", "manifest.json",
                         "failed_harness.json", "owned_cleanup.json", "metadata/pre_d04.json"):
            write_new(target / relative, {"schema": "ft_r057_file_probe/v1", "not_measurement": True,
                                           "purpose": "formal round output"})
        receipt = {"schema": "ft_r057_dry_run/v1", "rid": RID, "candidate_commit": CANDIDATE, "passed": True,
                   "owner": {"path": str(Path(__file__).resolve()), "uid": os.getuid(), "user": os.environ.get("USER")},
                   "cwd": os.getcwd(), "worktree": str(WT),
                   "source_sha256": packet(output_root)["required_sources"], "source_copies": sources, "formal_rid_directory_created": False,
                   "service_started": False, "requests_sent": False, "gpu_lock_taken": False, "batch_allocated": False,
                   "arms": plans}
        write_new(target / "dry_run_receipt.json", receipt)
        (target / "dry_run_receipt.json").chmod(0o444)
        return {**receipt, "dry_run_directory": str(target), "receipt_sha256": sha256(target / "dry_run_receipt.json")}
    except BaseException:
        raise


def archive_sources(run: Path) -> list[dict]:
    target = run / "runtime_sources"
    target.mkdir()
    rows = []
    for source in (Path(__file__).resolve(), WRAPPER_SOURCE, D07_SOURCE, FILE_PREP_SOURCE, PORT_SOURCE):
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("R057 runtime source unavailable: " + str(source))
        copy = target / source.name
        shutil.copyfile(source, copy)
        copy.chmod(0o444)
        rows.append({"source": str(source), "sha256": sha256(source), "copy": str(copy), "copy_sha256": sha256(copy)})
    return rows


def _readonly(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("R057 predecessor is absent, symlinked, or writable: " + str(path))


def _sealed(path: Path) -> dict:
    _readonly(path)
    return json.loads(path.read_text(encoding="utf-8"))


def predecessor_admission(d07) -> dict:
    # D07 performs the sealed pin/round/manifest/RO walk and invokes the
    # archived round_json_append.py `check`; do not guess a history filename.
    round_path = d07.require_closed_round("E2-R056", "measured")
    root, manifest = round_path.parent, round_path.parent / "MANIFEST.sha256"
    round_value = _sealed(round_path)
    return {"E2-R056": {"round": str(round_path), "round_sha256": sha256(round_path),
                           "manifest": str(manifest), "manifest_sha256": sha256(manifest),
                           "d04_history_check": "round_json_append.py check", "verdict": "measured"}}


def dry_run_path() -> Path:
    return ROUNDS / f".dryrun_R057a_v2_{RID}" / "dry_run_receipt.json"


def require_startup_review() -> dict:
    receipt = dry_run_path()
    value = _sealed(receipt)
    owner = {"path": str(Path(__file__).resolve()), "uid": os.getuid(), "user": os.environ.get("USER")}
    if (value.get("schema") != "ft_r057_dry_run/v1" or value.get("candidate_commit") != CANDIDATE or value.get("passed") is not True
            or value.get("owner") != owner or value.get("cwd") != str(ROOT) or value.get("worktree") != str(WT)
            or value.get("source_sha256") != packet()["required_sources"]
            or any(value.get(flag) is not False for flag in ("formal_rid_directory_created", "service_started", "requests_sent", "gpu_lock_taken", "batch_allocated"))):
        raise RuntimeError("R057 FILEDRY receipt differs")
    review = ROOT / "runs" / "dev_R057" / "reviews" / "E2-R057a_startup_review_v2.json"
    signed = _sealed(review)
    expected = {"schema": "ft_r057_startup_review/v1", "rid": RID, "candidate_commit": CANDIDATE,
                "approved": True, "verdict": "PASS", "dry_run_receipt": str(receipt),
                "dry_run_receipt_sha256": sha256(receipt), "source_sha256": value["source_sha256"]}
    if any(signed.get(key) != expected_value for key, expected_value in expected.items()):
        raise RuntimeError("R057 startup review binding differs")
    return {"path": str(review), "sha256": sha256(review)}


def _write_arm_files(d07, directory: Path, plan: dict) -> dict:
    prepared = load_file_prep().prepare_server_files(d07, directory, WT, plan["port"], None)
    env = prepared["env"]
    env.pop("FT_DEV_ROUTE_TRACE", None)
    env.pop("FT_DEV_PAUSE_ENDPOINT", None)
    env.update(plan["environment"])
    shutil.copyfile(WRAPPER_SOURCE, directory / WRAPPER_SOURCE.name)
    (directory / WRAPPER_SOURCE.name).chmod(0o444)
    prepared["argv"] = plan["startup_argv"]
    record = {key: env[key] for key in ("CUDA_VISIBLE_DEVICES", "PYTHONPATH", "VIRTUAL_ENV", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "FT_DEV_ROUTE_TRACE", "FT_DEV_PAUSE_ENDPOINT") if key in env}
    (directory / "ENV.json").write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "ENV.txt").write_text("".join(f"{key}={record[key]}\n" for key in sorted(record)), encoding="utf-8")
    (directory / "SERVE_CMD.txt").write_text("env " + " ".join(f"{key}={shlex.quote(value)}" for key, value in record.items()) + " " + shlex.join(prepared["argv"]) + "\n", encoding="utf-8")
    write_new(directory / "serve_argv.json", {"ft_argv": plan["ft_argv"], "startup_argv": plan["startup_argv"]})
    write_new(directory / "serve_args_diff.json", serve_args_diff(next(arm for arm in ARMS if arm["name"] == plan["arm"])))
    return prepared


def _start_arm(d07, directory: Path, plan: dict):
    prepared = _write_arm_files(d07, directory, plan)
    return load_file_prep().start_prepared_server(d07, directory, WT, plan["port"], prepared)


def _validate_args(directory: Path, arm: dict) -> None:
    text = (directory / "serve.log").read_text(encoding="utf-8", errors="replace")
    expected = ("memory_ratio=0.88", "kv_reserve_tokens=98304", "max_seq_len_override=98304", f"cuda_graph_max_bs={arm['cuda_graph_max_bs']}")
    if any(item not in text for item in expected):
        raise RuntimeError("R057 parsed ServerArgs differs from arm declaration")
    if arm["trace"] != ("CUDA graph disabled for development route trace" in text):
        raise RuntimeError("R057 trace/graph runtime marker differs")
    (directory / "serve_args.txt").write_text(text[text.find("Parsed arguments"):], encoding="utf-8")


def _is_oom(error: BaseException, directory: Path) -> bool:
    text = repr(error)
    log = directory / "serve.log"
    if log.exists():
        text += log.read_text(encoding="utf-8", errors="replace")
    return "out of memory" in text.lower() or "cuda oom" in text.lower()


def _require_32064_usage(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    record = value.get("record")
    if not isinstance(record, dict) or record.get("prompt_tokens") != PROMPT_TOKENS or record.get("cached_tokens") != 0:
        raise RuntimeError("R057 cold request lacks actual 32064-token cold usage evidence")
    if not isinstance(record.get("completion_tokens"), int) or not 0 < record["completion_tokens"] <= 128:
        raise RuntimeError("R057 cold completion-token count differs")
    if record.get("finish_reason") not in ("stop", "length", "tool_calls"):
        raise RuntimeError("R057 cold finish reason differs")


def snapshot_evidence(directory: Path, expected_event: str) -> dict:
    root, index = directory / "memory_history", directory / "memory_history" / "snapshots.jsonl"
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    matching = [row for row in rows if row.get("event") == expected_event]
    if len(matching) != 1:
        raise RuntimeError("R057 snapshot event is missing or ambiguous: " + expected_event)
    snapshot = Path(matching[0].get("path", ""))
    if snapshot.parent != root or snapshot.suffix != ".pickle" or snapshot.is_symlink() or not snapshot.is_file() or snapshot.stat().st_size <= 0:
        raise RuntimeError("R057 snapshot pickle differs")
    return {"event": expected_event, "path": str(snapshot), "sha256": sha256(snapshot), "time_ns": matching[0].get("time_ns")}


def _cleanup(d07, process, directory: Path, active: BaseException | None) -> None:
    if process is None:
        return
    if getattr(active, "owned_cleanup_failed", False):
        return
    try:
        lifecycle = d07.load_owned_lifecycle()
        lifecycle.stop_owned_process(process)
        if lifecycle.owned_group_alive(process.pid):
            raise RuntimeError("R057 owned process group remains alive")
        write_new(directory / "owned_cleanup.json", {"pid": process.pid, "cleaned": True})
    except BaseException as cleanup_error:
        cleanup_error.owned_process = process
        cleanup_error.owned_cleanup_failed = True
        raise


def invoke_bound_cold(d07, directory: Path, port: int) -> None:
    captured = 0
    payload = directory / "cold_request_payload.json"
    original = urllib.request.urlopen
    def capture(request, *args, **kwargs):
        nonlocal captured
        data = getattr(request, "data", None)
        if isinstance(data, bytes):
            captured += 1
            if captured != 1:
                raise RuntimeError("R057 cold request payload capture is ambiguous")
            # Preserve the exact request before urlopen can raise an OOM.  This
            # is intentionally outside the frozen helper rather than a mock.
            payload.write_bytes(data)
            if sha256(payload) != EXPECTED_INPUT_SHA:
                raise RuntimeError("R057a input differs from independently reviewed A/B request")
            write_new(directory / "cold_request_binding.json", {"payload": str(payload), "payload_sha256": sha256(payload),
                                                                  "cold_id": COLD_ID, "target_prompt_tokens": PROMPT_TOKENS})
        return original(request, *args, **kwargs)
    urllib.request.urlopen = capture
    try:
        d07.invoke_cold_eq(WT, port, COLD_ID, directory / "cold.json")
    finally:
        urllib.request.urlopen = original
    if captured != 1 or not payload.is_file():
        raise RuntimeError("R057 cold request payload capture is missing or ambiguous")


def run_arms(d07, run: Path) -> list[dict]:
    results = []
    for arm in ARMS:
        directory, process = run / arm["name"], None
        plan = arm_plan(arm, dynamic_port(), run)
        try:
            process = _start_arm(d07, directory, plan)
            _validate_args(directory, arm)
            write_new(directory / "cold_input_binding.json", {"cold_id": COLD_ID, "target_prompt_tokens": PROMPT_TOKENS,
                                                               "cold_helpers": d07.verify_frozen_cold_helpers()})
            invoke_bound_cold(d07, directory, plan["port"])
            _require_32064_usage(directory / "cold.json")
            result = {"arm": arm["name"], "status": "completed", "cold": "cold.json", "cold_input_binding": "cold_input_binding.json", "snapshot": snapshot_evidence(directory, "request_after")}
        except BaseException as error:
            process = getattr(error, "owned_process", process)
            if _is_oom(error, directory):
                result = {"arm": arm["name"], "status": "oom", "error": repr(error), "snapshot": snapshot_evidence(directory, "request_error")}
            else:
                write_new(directory / "error.json", {"arm": arm["name"], "error": repr(error), "non_oom": True})
                error.owned_process = process
                raise
        finally:
            active = sys.exc_info()[1]
            _cleanup(d07, process, directory, active)
        write_new(directory / "arm_result.json", result)
        results.append(result)
    return results


def child_argv(batch: int, receipt: Path) -> list[str]:
    return [str(VENV / "bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child", "--batch", str(batch), "--launch-receipt", str(receipt)]


def execute(*, owned_child: bool = False, batch: int | None = None, launch_receipt: Path | None = None) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("R057 --run requires Linux GPU host")
    d07 = load_d07()
    # Check all immutable prerequisites before a controller can consume a batch.
    preflight = packet()
    d07.checked_worktree(WT)
    review, predecessors = require_startup_review(), predecessor_admission(d07)
    d07.require_closed_round("E2-R057", "failed_harness")
    predecessors["preserved_R057"] = {"rid": "E2-R057", "round_sha256": sha256(ROUNDS / "E2-R057/round.json"), "manifest_sha256": sha256(ROUNDS / "E2-R057/MANIFEST.sha256"), "completed_arms": ["A_trace_on_pause_off", "B_trace_off_pause_on"]}
    if not owned_child:
        if d07.LOCK.exists() or d07.LOCK.is_symlink():
            raise RuntimeError("R057 foreign GPU lock; remain queued")
        owned = d07.load_owned_lifecycle()
        helper = owned.verified_module(ROOT / "runs" / "plan_batches" / "e2_launch.py", d07.ATOMIC_HELPER_SHA, "r057_atomic")
        selected = helper.next_batch(ROUNDS)
        receipt = ROOT / "runs" / "dev_R057" / f"launch_{RID}_batch{selected}.json"
        argv = child_argv(selected, receipt)
        reserved = {"schema": "ft_r057_owned_launch/v1", "state": "reserved", "rid": RID, "batch": selected,
                    "candidate_commit": CANDIDATE, "argv_sha256": d07.argv_sha256(argv), "controller": d07.process_birth()}
        launched = owned.reserve_process(helper, selected, RID, argv, receipt, reserved)
        birth = owned.process_identity(launched["batch_pid"])
        if birth is None:
            raise RuntimeError("R057 reserved child birth unavailable")
        return d07.publish_child_binding(receipt, launched, {key: birth[key] for key in ("pid", "start_ticks", "execution_id")}, lifecycle=owned)
    if batch is None or launch_receipt is None:
        raise RuntimeError("R057 child requires batch and launch receipt")
    d07.require_child_receipt(launch_receipt, batch, WT, ROUNDS, rid=RID, expected_argv=child_argv(batch, launch_receipt), schema="ft_r057_owned_launch/v1")
    owner, run, preserve_lock = d07.take_d07_gpu_lock(RID, batch), None, False
    try:
        d07.require_gpu_idle()
        run = ROUNDS / RID
        if run.exists():
            raise RuntimeError("R057 formal directory already exists")
        run.mkdir(mode=0o700)
        sources = archive_sources(run)
        write_new(run / "preflight.json", {"packet": preflight, "batch": batch, "gpu_owner": owner, "startup_review": review, "predecessors": predecessors, "sources": sources})
        arms = run_arms(d07, run)
        write_new(run / "result.json", {"schema": "ft_r057_oom_diagnostic_raw/v1", "rid": RID, "candidate_commit": CANDIDATE,
                                          "verdict": "pending_diagnostic", "diagnostic_only": True, "preserved_round": "E2-R057", "cold_id": COLD_ID, "arms": arms})
        manifest = {path.relative_to(run).as_posix(): sha256(path) for path in run.rglob("*") if path.is_file()}
        write_new(run / "manifest.json", {"schema": "ft_r057_manifest/v1", "files": manifest})
        return json.loads((run / "result.json").read_text())
    except BaseException as error:
        preserve_lock = bool(getattr(error, "owned_cleanup_failed", False))
        if run is not None:
            write_new(run / "failed_harness.json", {"rid": RID, "batch": batch, "error": repr(error), "raw_preserved": True, "owned_cleanup_failed": preserve_lock})
        raise
    finally:
        if not preserve_lock:
            d07.release_d07_gpu_lock(owner)
        if run is not None:
            write_new(run / "owned_cleanup.json", {"rid": RID, "batch": batch, "lock_released": not preserve_lock, "owned_cleanup_failed": preserve_lock})


def self_test() -> None:
    assert len(ARMS) == 2
    assert COLD_ID == "E2-R057"
    assert [(arm["trace"], arm["pause"], arm["cuda_graph_max_bs"]) for arm in ARMS] == [(True, True, 2), (False, False, 0)]
    assert MEMORY_RATIO == "0.88" and WINDOW == 98304 and PROMPT_TOKENS == 32064
    assert all("8095" not in arm["name"] for arm in ARMS)
    print("SELFTEST PASS: R057a remaining C/D arms with original input ID and port-pair probe at 98304/.88 with 32064 cold prompt")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--run", action="store_true")
    choice.add_argument("--file-dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--owned-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--batch", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--launch-receipt", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--output-root", type=Path, default=ROUNDS)
    options = parser.parse_args(argv)
    if options.self_test:
        if options.file_dry_run or options.run:
            parser.error("--self-test cannot mix with execution")
        self_test()
        return 0
    if options.owned_child and not options.run:
        parser.error("--owned-child requires --run")
    value = execute(owned_child=options.owned_child, batch=options.batch, launch_receipt=options.launch_receipt) if options.run else file_dry_run(options.output_root) if options.file_dry_run else packet(options.output_root)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
