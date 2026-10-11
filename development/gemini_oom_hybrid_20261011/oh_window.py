#!/usr/bin/env python3
"""Window orchestration tool for Gemini OOM & Hybrid verification (P1-G3).

Executes the approved window plan (PLAN.json) across 6 services:
S1 (O-warm), S2 (O-fresh), S3 (HR-a), S4 (HR-b), S5 (HR-b-fresh), S6 (H-stats).
Provides exact argv gating, service lifecycle management, AIPerf speed measurement,
OpenAI SDK streaming ladder with OOM detection, output text comparison, and D0 stats reading.
Supports full rehearsal mode (--rehearse) with stub server.
"""
from __future__ import annotations

import argparse
import copy
import glob
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Ensure release-e2 and hybrid_verify are in sys.path
HYBRID_VERIFY_DIR = Path("/data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify")
if HYBRID_VERIFY_DIR.exists() and str(HYBRID_VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(HYBRID_VERIFY_DIR))

try:
    import hybrid_service
    from hybrid_service import alive_members, capture_birth, cleanup, idle, load_d07
except ImportError:
    hybrid_service = None  # Handled in unit tests if mocking


AIPERF_BIN = "/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf"
VENV_EVAL_PYTHON = "/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python"
RELEASE_PYTHONPATH = "/data2/FreeToken/wt/release-e2/python"
MODEL_NAME = "Qwen3.8-Flash-Next-NVFP4"
SERVER_URL = "http://127.0.0.1:8123"


def first_diff(a: str, b: str) -> int | None:
    """Find the 0-indexed position of the first differing character, or None if identical."""
    limit = min(len(a), len(b))
    for i in range(limit):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return limit
    return None


def extract_output_text_from_record(rec: dict[str, Any]) -> str:
    """Extract full generation text from an AIPerf raw record."""
    text = ""
    for resp in rec.get("responses", []):
        for pkt in resp.get("packets", []):
            val = pkt.get("value", "")
            if not val.startswith("{"):
                continue
            try:
                data = json.loads(val)
            except Exception:
                continue
            for choice in data.get("choices", []):
                delta = choice.get("delta", {})
                r = delta.get("reasoning_content") or ""
                c = delta.get("content") or ""
                tc = delta.get("tool_calls")
                tc_str = json.dumps(tc, ensure_ascii=False) if tc else ""
                text += r + c + tc_str
    return text


def extract_outputs_from_phase_dir(phase_dir: Path) -> list[dict[str, Any]]:
    """Extract outputs.json records from an AIPerf phase directory."""
    raw_files = list(phase_dir.glob("raw_records/*.jsonl"))
    if not raw_files:
        single_raw = phase_dir / "profile_export_raw.jsonl"
        if single_raw.exists():
            raw_files = [single_raw]

    if not raw_files:
        raise FileNotFoundError(f"No raw AIPerf records found in {phase_dir}")

    records = []
    for fpath in raw_files:
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                meta = rec.get("metadata", {})
                session_num = meta.get("session_num", 0)
                x_req_id = meta.get("x_request_id") or rec.get("request_headers", {}).get("X-Request-ID")
                text = extract_output_text_from_record(rec)
                sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                records.append({
                    "input_index": session_num,
                    "x_request_id": x_req_id,
                    "text": text,
                    "char_count": len(text),
                    "sha256": sha,
                })

    records.sort(key=lambda x: x["input_index"])
    return records


def compute_expected_argv(baseline: list[str], service_spec: dict[str, Any], host: str = "127.0.0.1", port: int = 8123) -> list[str]:
    """Compute the approved argv for a given service specification against baseline."""
    mode = service_spec.get("type", "offload")
    extra_argv = service_spec.get("extra_argv", [])

    if baseline[:3] != ["taskset", "-c", "1,3-47"]:
        raise ValueError("unexpected baseline affinity prefix")

    tail = list(baseline[3:])
    for flag, value in (("--host", str(host)), ("--port", str(port))):
        if tail.count(flag) != 1:
            raise ValueError(f"unexpected baseline {flag} count")
        tail[tail.index(flag) + 1] = value

    if mode == "offload":
        res = ["taskset", "-c", "1,3-47", *tail]
    elif mode == "hybrid":
        if tail.count("--moe-strategy") != 1 or tail[tail.index("--moe-strategy") + 1] != "offload":
            raise ValueError("unexpected baseline strategy")
        tail[tail.index("--moe-strategy") + 1] = "hybrid"
        res = ["numactl", "--interleave=all", "taskset", "-c", "1,3-23,25,27-47", *tail]
    else:
        raise ValueError(f"unknown service mode: {mode}")

    if extra_argv:
        res = [*res, *extra_argv]
    return res


def validate_argv_diff(baseline: list[str], actual: list[str]) -> list[dict[str, Any]]:
    """Validate that actual argv differs from baseline only in approved dimensions.

    Approved differences:
    1. --host / --port moved to 127.0.0.1:8123
    2. hybrid: numactl --interleave=all taskset -c 1,3-23,25,27-47 and --moe-strategy hybrid
    3. --moe-hybrid-max-fetch 0 appended
    """
    diff = []
    width = max(len(baseline), len(actual))
    for idx in range(width):
        old = baseline[idx] if idx < len(baseline) else None
        new = actual[idx] if idx < len(actual) else None
        if old != new:
            diff.append({"index": idx, "baseline": old, "actual": new})

    # Validate that actual can be produced by compute_expected_argv
    # Determine mode:
    is_hybrid = ("numactl" in actual and "--moe-strategy" in actual and actual[actual.index("--moe-strategy")+1] == "hybrid")
    mode = "hybrid" if is_hybrid else "offload"

    extra = []
    if "--moe-hybrid-max-fetch" in actual:
        idx = actual.index("--moe-hybrid-max-fetch")
        if idx == len(actual) - 2 and actual[idx + 1] == "0":
            extra = ["--moe-hybrid-max-fetch", "0"]
        else:
            raise ValueError(f"invalid --moe-hybrid-max-fetch argument placement: {actual[idx:]}")

    expected = compute_expected_argv(baseline, {"type": mode, "extra_argv": extra})
    if actual != expected:
        raise ValueError(f"unapproved argv differences from baseline. Diff: {diff}")

    return diff


def check_is_oom_chunk(chunk_dict: dict[str, Any]) -> tuple[bool, str]:
    """Check if an SSE chunk response indicates CUDA OOM."""
    err = chunk_dict.get("error")
    if err and isinstance(err, dict):
        msg = str(err.get("message", "")).lower()
        if "out of memory" in msg or "worker_restarting_after_oom" in msg:
            return True, err.get("message", "")
    return False, ""


def query_gpu_memory_used() -> int:
    """Query current GPU memory used in MiB via nvidia-smi."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        )
        return int(out.strip().split("\n")[0].strip())
    except Exception:
        return -1


def check_preconditions(rehearse: bool = False) -> None:
    """Check window preconditions before starting."""
    if rehearse:
        return

    # 1. Check production 8095 port
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("172.16.108.9", 8095))
        except OSError as exc:
            raise RuntimeError(f"172.16.108.9:8095 cannot be bound: {exc}")

    # 2. Check no ft serve process
    try:
        out = subprocess.check_output(["pgrep", "-f", "ft serve"], text=True)
        if out.strip():
            raise RuntimeError(f"ft serve processes still running: {out.strip()}")
    except subprocess.CalledProcessError:
        pass  # pgrep returns 1 when no process found

    # 3. Check gpu.lock absent
    if os.path.exists("/data2/_shared/gpu.lock"):
        raise RuntimeError("/data2/_shared/gpu.lock exists")

    # 4. Check compute apps empty
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
            text=True,
        )
        if out.strip():
            raise RuntimeError(f"compute processes found on GPU: {out.strip()}")
    except Exception as exc:
        raise RuntimeError(f"failed to query compute processes: {exc}")


def run_ladder_step(
    step_name: str,
    payload_path: Path,
    run_id: str,
    step_idx: int,
    service_dir: Path,
    rehearse: bool = False,
) -> dict[str, Any]:
    """Execute a single ladder step using OpenAI SDK."""
    with open(payload_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    messages = copy.deepcopy(payload.get("messages", []))
    tools = payload.get("tools")

    cold_marker = f"[gemini-oom run={run_id} step={step_name} n={step_idx}]\n"
    if messages and "content" in messages[0]:
        messages[0]["content"] = cold_marker + (messages[0]["content"] or "")

    mem_before = query_gpu_memory_used() if not rehearse else 0

    t_start = time.monotonic()
    first_token_time = None
    finish_reason = None
    prompt_tokens = None
    completion_tokens = 0
    oom_detected = False
    oom_error_msg = ""
    chunks_count = 0

    import httpx
    import openai

    http_client = httpx.Client(trust_env=False, timeout=600.0)
    client = openai.OpenAI(base_url="http://127.0.0.1:8123/v1", api_key="none", http_client=http_client)

    try:
        stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            max_tokens=32,
            temperature=0.0,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            chunks_count += 1
            now = time.monotonic()
            if first_token_time is None:
                first_token_time = now - t_start

            c_dict = chunk.model_dump()
            is_oom, err_msg = check_is_oom_chunk(c_dict)
            if is_oom:
                oom_detected = True
                oom_error_msg = err_msg
                break

            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens

            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

    except Exception as exc:
        err_str = str(exc).lower()
        if "out of memory" in err_str or "worker_restarting_after_oom" in err_str:
            oom_detected = True
            oom_error_msg = str(exc)
        else:
            raise

    mem_after = query_gpu_memory_used() if not rehearse else 0

    recovery_seconds = None
    if oom_detected:
        # Capture ~40 lines of serve.log around this moment
        serve_log_path = service_dir / "serve.log"
        oom_log_path = service_dir / f"oom_{step_name}.log"
        if serve_log_path.exists():
            lines = serve_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail_lines = lines[-40:] if len(lines) >= 40 else lines
            oom_log_path.write_text("\n".join(tail_lines) + "\n", encoding="utf-8")

        # Poll /health every 5s until serving (max 300s)
        t_rec_start = time.monotonic()
        while time.monotonic() - t_rec_start < 300.0:
            time.sleep(5.0)
            try:
                import urllib.request
                req = urllib.request.urlopen("http://127.0.0.1:8123/health", timeout=5)
                data = json.loads(req.read().decode("utf-8"))
                if data.get("status") == "ok" and data.get("maintenance") == "serving":
                    recovery_seconds = round(time.monotonic() - t_rec_start, 2)
                    break
            except Exception:
                pass

    return {
        "step": step_name,
        "cold_marker": cold_marker.strip(),
        "chunks_count": chunks_count,
        "first_token_time_s": round(first_token_time, 4) if first_token_time else None,
        "finish_reason": finish_reason,
        "usage_prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "oom_detected": oom_detected,
        "oom_error": oom_error_msg,
        "recovery_seconds": recovery_seconds,
        "gpu_mem_before_mib": mem_before,
        "gpu_mem_after_mib": mem_after,
        "duration_s": round(time.monotonic() - t_start, 2),
    }


def execute_window(
    plan_path: Path,
    out_dir: Path,
    rehearse: bool = False,
    stub_threshold: int = -1,
    stub_non_deterministic: bool = False,
) -> int:
    """Main window executor."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    with open(plan["baseline_freeze_path"], "r", encoding="utf-8") as f:
        baseline_data = json.load(f)
    baseline_argv = baseline_data["argv"]

    check_preconditions(rehearse=rehearse)

    d07 = None
    if not rehearse:
        d07 = load_d07()
    else:
        # Load real d07 and stub only 3 GPU methods as required by P1-G5:
        # take_d07_gpu_lock, release_d07_gpu_lock, require_gpu_idle.
        # process_identity retains its real implementation.
        try:
            d07 = load_d07()
            d07.take_d07_gpu_lock = lambda name, batch: f"STUB-LOCK-{name}"
            d07.release_d07_gpu_lock = lambda owner: None
            d07.require_gpu_idle = lambda: None
        except Exception:
            from types import SimpleNamespace
            d07 = SimpleNamespace(
                take_d07_gpu_lock=lambda name, batch: f"STUB-LOCK-{name}",
                release_d07_gpu_lock=lambda owner: None,
                require_gpu_idle=lambda: None,
                process_identity=lambda pid: {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1},
            )
        # Monkey patch hybrid_service.idle to avoid checking GPU during rehearsal
        if hybrid_service:
            def stub_idle(d07_obj, checks=()):
                for host, port in checks:
                    with socket.socket() as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind((host, port))
            hybrid_service.idle = stub_idle

    window_start_time = time.monotonic()
    window_limit = plan.get("window_limit_seconds", 6600)
    cutoff_reserve = plan.get("service_cutoff_reserve_seconds", 900)

    summary: dict[str, Any] = {
        "schema": "gemini_oom_hybrid_window_summary/v1",
        "plan": plan_path.name,
        "rehearse": rehearse,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "services": {},
        "verdict": "running",
    }

    for s_idx, service in enumerate(plan["services"]):
        elapsed = time.monotonic() - window_start_time
        remaining = window_limit - elapsed
        if remaining < cutoff_reserve:
            print(f"Skipping service {service['name']}: remaining time {remaining:.1f}s < {cutoff_reserve}s")
            break

        s_name = service["name"]
        s_dir = out_dir / s_name
        s_dir.mkdir(parents=True, exist_ok=True)

        # 1. Compute and validate argv
        expected_argv = compute_expected_argv(baseline_argv, service)
        argv_diff = validate_argv_diff(baseline_argv, expected_argv)
        with open(s_dir / "argv_diff.json", "w", encoding="utf-8") as f:
            json.dump({
                "baseline": baseline_argv,
                "actual": expected_argv,
                "service": s_name,
                "mode": service.get("type"),
                "diff": argv_diff,
            }, f, indent=2)

        # 2. Build environment
        env = dict(os.environ)
        # Remove all FT_DEV_ keys
        for k in list(env.keys()):
            if k.startswith("FT_DEV_"):
                del env[k]
        env["PYTHONPATH"] = RELEASE_PYTHONPATH
        env["MASTER_PORT"] = "8096"
        env["CUDA_VISIBLE_DEVICES"] = "0"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        # Apply service extra env
        for k, v in service.get("extra_env", {}).items():
            if "<SERVICE_OUT>" in v:
                v = v.replace("<SERVICE_OUT>", str(s_dir))
            env[k] = v

        # 3. Determine spawn argv
        if not rehearse:
            spawn_argv = expected_argv
        else:
            stub_script = Path(__file__).with_name("stub_server.py")
            spawn_argv = [
                sys.executable,
                str(stub_script),
                "--host", "127.0.0.1",
                "--port", "8123",
                "--oom-threshold", str(stub_threshold),
            ]
            if stub_non_deterministic:
                spawn_argv.append("--non-deterministic")

        # 4. Check idle and take lock
        if not rehearse:
            idle(d07, [("127.0.0.1", 8123)])
        lock_owner = d07.take_d07_gpu_lock(f"GEMINI-OOM-HYBRID-20261011-{s_name}", 0)

        # 5. Spawn service
        serve_log = open(s_dir / "serve.log", "wb")
        proc = subprocess.Popen(
            spawn_argv,
            cwd=s_dir,
            env=env,
            stdout=serve_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        birth = capture_birth(proc, d07)

        # 6. Wait for ready
        ready = False
        moe_cache_size = None
        t0 = time.monotonic()
        while time.monotonic() - t0 < 600.0:
            time.sleep(1.0)
            try:
                import urllib.request
                req = urllib.request.urlopen("http://127.0.0.1:8123/health", timeout=2)
                data = json.loads(req.read().decode("utf-8"))
                if data.get("status") == "ok" and data.get("maintenance") == "serving":
                    ready = True
                    break
            except Exception:
                pass

        if not ready:
            print(f"Service {s_name} failed to become ready within 600s")

        # Check moe_cache_size in serve.log
        serve_log.flush()
        try:
            with open(s_dir / "serve.log", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "moe_cache_size=" in line:
                        for token in line.split():
                            if token.startswith("moe_cache_size="):
                                moe_cache_size = token.split("=")[1].strip()
        except Exception:
            pass

        # 7. Execute phases
        phases_results: dict[str, Any] = {}
        service_abnormal_speed = False

        if ready:
            for phase in service.get("phases", []):
                p_type = phase.get("type")
                p_name = phase.get("name")
                p_dir = s_dir / p_name
                p_dir.mkdir(parents=True, exist_ok=True)

                if p_type == "warmup":
                    # Run 2 warmup runs
                    for w_idx in [1, 2]:
                        w_dir = s_dir / f"warmup_{w_idx}"
                        w_dir.mkdir(parents=True, exist_ok=True)
                        w_in = w_dir / "input_lane0.jsonl"
                        inputs_x = Path(__file__).with_name("inputs") / "inputs_X.jsonl"
                        with open(inputs_x, "rb") as fi, open(w_in, "wb") as fo:
                            fo.write(fi.readline())
                        w_cmd = [
                            AIPERF_BIN, "profile",
                            "--model", MODEL_NAME,
                            "--endpoint-type", "chat",
                            "--streaming",
                            "--url", SERVER_URL,
                            "--input-file", str(w_in),
                            "--custom-dataset-type", "single_turn",
                            "--dataset-sampling-strategy", "sequential",
                            "--request-count", "1",
                            "--concurrency", "1",
                            "--wait-for-model-timeout", "0",
                            "--request-timeout-seconds", "180",
                            "--no-server-metrics", "--no-gpu-telemetry", "--ui", "none",
                            "--tokenizer", "builtin",
                            "--use-server-token-count", "--use-legacy-max-tokens",
                            "--export-level", "raw",
                            "--output-artifact-dir", str(w_dir),
                        ]
                        subprocess.run(w_cmd, capture_output=True, timeout=180)
                    phases_results[p_name] = {"status": "warmup_completed"}

                elif p_type == "x_aiperf":
                    if service_abnormal_speed:
                        phases_results[p_name] = {"status": "skipped_due_to_abnormal_speed"}
                        continue

                    conc = phase.get("concurrency", 1)
                    req_cnt = phase.get("request_count", 1)
                    inputs_x = Path(__file__).with_name("inputs") / "inputs_X.jsonl"

                    if conc == 1:
                        target_input = p_dir / "input_lane0.jsonl"
                        with open(inputs_x, "rb") as fi, open(target_input, "wb") as fo:
                            fo.write(fi.readline())
                    else:
                        target_input = inputs_x

                    aiperf_cmd = [
                        AIPERF_BIN, "profile",
                        "--model", MODEL_NAME,
                        "--endpoint-type", "chat",
                        "--streaming",
                        "--url", SERVER_URL,
                        "--input-file", str(target_input),
                        "--custom-dataset-type", "single_turn",
                        "--dataset-sampling-strategy", "sequential",
                        "--request-count", str(req_cnt),
                        "--concurrency", str(conc),
                        "--wait-for-model-timeout", "0",
                        "--request-timeout-seconds", "180",
                        "--no-server-metrics", "--no-gpu-telemetry", "--ui", "none",
                        "--tokenizer", "builtin",
                        "--use-server-token-count", "--use-legacy-max-tokens",
                        "--export-level", "raw",
                        "--output-artifact-dir", str(p_dir),
                    ]
                    with open(p_dir / "command.json", "w", encoding="utf-8") as f:
                        json.dump(aiperf_cmd, f, indent=2)

                    t_p_start = time.monotonic()
                    p_res = subprocess.run(aiperf_cmd, capture_output=True, timeout=180)
                    t_p_duration = time.monotonic() - t_p_start

                    # Parse profile_export.jsonl
                    profile_file = p_dir / "profile_export.jsonl"
                    speed_list = []
                    tokens_valid = True
                    if profile_file.exists():
                        with open(profile_file, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                prow = json.loads(line)
                                m = prow.get("metrics", {})
                                itl = m.get("inter_token_latency", {}).get("value")
                                if itl and itl > 0:
                                    speed_list.append(round(1000.0 / itl, 2))
                                out_tokens = m.get("output_sequence_length", {}).get("value", 0)
                                if out_tokens != 256:
                                    tokens_valid = False

                    # Extract outputs.json
                    try:
                        outputs_list = extract_outputs_from_phase_dir(p_dir)
                        with open(p_dir / "outputs.json", "w", encoding="utf-8") as f:
                            json.dump(outputs_list, f, indent=2)
                    except Exception as exc:
                        outputs_list = []

                    # Speed abnormal check
                    abnormal = any(s < 7.8 for s in speed_list)
                    if abnormal:
                        service_abnormal_speed = True

                    phases_results[p_name] = {
                        "exit_code": p_res.returncode,
                        "duration_s": round(t_p_duration, 2),
                        "speed_tok_s": speed_list,
                        "tokens_valid": tokens_valid,
                        "abnormal": abnormal,
                        "outputs_count": len(outputs_list),
                    }

                elif p_type == "ladder":
                    ladder_rows = []
                    steps = phase.get("steps", [])
                    ladder_file = s_dir / "ladder.jsonl"
                    inputs_dir = Path(__file__).with_name("inputs")

                    with open(ladder_file, "w", encoding="utf-8") as f_lad:
                        for idx, st_name in enumerate(steps):
                            st_path = inputs_dir / f"{st_name}.json"
                            res_step = run_ladder_step(
                                step_name=st_name,
                                payload_path=st_path,
                                run_id=f"{s_name}-{int(time.time())}",
                                step_idx=idx,
                                service_dir=s_dir,
                                rehearse=rehearse,
                            )
                            ladder_rows.append(res_step)
                            f_lad.write(json.dumps(res_step) + "\n")
                            f_lad.flush()

                            # If OOM detected, stop ladder immediately!
                            if res_step.get("oom_detected"):
                                print(f"Ladder step {st_name} triggered OOM. Stopping ladder.")
                                break

                    phases_results[p_name] = {
                        "completed_steps": len(ladder_rows),
                        "results": ladder_rows,
                    }

                elif p_type == "compare":
                    target_a = phase.get("target_a")
                    target_b = phase.get("target_b")
                    a_dir = out_dir / target_a
                    b_dir = out_dir / target_b

                    with open(a_dir / "outputs.json", "r", encoding="utf-8") as f:
                        outs_a = json.load(f)
                    with open(b_dir / "outputs.json", "r", encoding="utf-8") as f:
                        outs_b = json.load(f)

                    comp_results = []
                    all_identical = True
                    for rec_a, rec_b in zip(outs_a, outs_b):
                        text_a = rec_a.get("text", "")
                        text_b = rec_b.get("text", "")
                        d_pos = first_diff(text_a, text_b)
                        is_same = (d_pos is None)
                        if not is_same:
                            all_identical = False
                        comp_results.append({
                            "input_index": rec_a.get("input_index"),
                            "identical": is_same,
                            "first_diff_char": d_pos,
                            "len_a": len(text_a),
                            "len_b": len(text_b),
                        })

                    with open(p_dir / "compare.json", "w", encoding="utf-8") as f:
                        json.dump({
                            "target_a": target_a,
                            "target_b": target_b,
                            "all_identical": all_identical,
                            "comparisons": comp_results,
                        }, f, indent=2)

                    phases_results[p_name] = {
                        "all_identical": all_identical,
                        "comparisons": comp_results,
                    }

                elif p_type == "d0_read":
                    time.sleep(5.0)
                    d0_decode_path = s_dir / "d0_decode.json"
                    d0_steps_path = s_dir / "d0_decode_steps.jsonl"

                    steps_miss_rate = None
                    missing_total_field_present = True
                    field_error_msg = None

                    if d0_steps_path.exists():
                        step_rows = []
                        with open(d0_steps_path, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    step_rows.append(json.loads(line))

                        # Exclude first 16 steps
                        post16_steps = [r for r in step_rows if r.get("step", 0) >= 16]
                        if post16_steps:
                            # Verify missing_total field
                            if all("missing_total" in r for r in post16_steps):
                                tot_missing = sum(r["missing_total"] for r in post16_steps)
                                denom = len(post16_steps) * 480
                                steps_miss_rate = round(tot_missing / denom, 4)
                            else:
                                missing_total_field_present = False
                                field_error_msg = f"字段不同: keys={[list(r.keys()) for r in post16_steps[:2]]}"

                    decode_info = {}
                    if d0_decode_path.exists():
                        with open(d0_decode_path, "r", encoding="utf-8") as f:
                            decode_info = json.load(f)

                    d0_summary = {
                        "steps_miss_rate": steps_miss_rate,
                        "missing_total_present": missing_total_field_present,
                        "field_error": field_error_msg,
                        "fetched_per_layer": decode_info.get("fetched_per_layer"),
                        "cpu_per_layer": decode_info.get("cpu_per_layer"),
                        "decode_miss_rate": decode_info.get("miss_rate"),
                    }
                    with open(p_dir / "d0_summary.json", "w", encoding="utf-8") as f:
                        json.dump(d0_summary, f, indent=2)

                    phases_results[p_name] = d0_summary

        # 8. Cleanup
        cleanup_proved = cleanup(proc, birth, d07, s_dir, [("127.0.0.1", 8123)])
        lock_retained = False
        if cleanup_proved:
            d07.release_d07_gpu_lock(lock_owner)
        else:
            lock_retained = True
            with open(out_dir / "CLEANUP_BLOCKED.md", "w", encoding="utf-8") as f:
                f.write(f"# Cleanup Blocked for {s_name}\n\nLock retained: {lock_owner}\n")
            print(f"Cleanup failed for {s_name}! Halting window.")

        # 9. Write service terminal.json
        s_term = {
            "service": s_name,
            "ready": ready,
            "moe_cache_size": moe_cache_size,
            "phases": phases_results,
            "cleanup_proved": cleanup_proved,
            "lock_retained": lock_retained,
        }
        with open(s_dir / "terminal.json", "w", encoding="utf-8") as f:
            json.dump(s_term, f, indent=2)

        summary["services"][s_name] = s_term

        if not cleanup_proved:
            summary["verdict"] = "cleanup_blocked"
            break

    summary["verdict"] = "completed" if summary["verdict"] == "running" else summary["verdict"]
    summary["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    summary["duration_s"] = round(time.monotonic() - window_start_time, 2)

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    with open(out_dir / "terminal.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini OOM & Hybrid Window Runner")
    parser.add_argument("--execute", action="store_true", help="Execute real window on GPU")
    parser.add_argument("--rehearse", action="store_true", help="Execute rehearsal on CPU with stub server")
    parser.add_argument("--plan", default="PLAN.json", help="Path to PLAN.json")
    parser.add_argument("--out", required=True, help="Output runs directory")
    parser.add_argument("--stub-threshold", type=int, default=-1, help="Stub server OOM character threshold")
    parser.add_argument("--stub-non-deterministic", action="store_true", help="Stub server non-deterministic mode")

    args = parser.parse_args()

    if not args.execute and not args.rehearse:
        parser.error("Must specify either --execute or --rehearse")

    ret = execute_window(
        plan_path=Path(args.plan).resolve(),
        out_dir=Path(args.out).resolve(),
        rehearse=args.rehearse,
        stub_threshold=args.stub_threshold,
        stub_non_deterministic=args.stub_non_deterministic,
    )
    sys.exit(ret)


if __name__ == "__main__":
    main()
