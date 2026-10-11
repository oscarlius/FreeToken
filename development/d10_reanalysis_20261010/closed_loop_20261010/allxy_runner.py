"""Default-inert, root-admitted one-phase X/Y closed-loop measurement runner."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path

AIPERF = "/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf"
MODEL, GROUPS = "Qwen3.8-Flash-Next-NVFP4", ("X", "Y")
LIMITS = {"speed": 180, "d0": 480}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows(path): return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]

def check_inputs(path, group):
    values, expected = rows(path), 256 if group == "X" else 128
    if len(values) != 2: raise ValueError(f"{group} needs exactly two inputs")
    for value in values:
        if value.get("output_length") != expected or value.get("extra") != {"temperature": 0, "top_p": 1, "ignore_eos": False}:
            raise ValueError(f"{group} frozen input contract differs")

def proc_snapshot(pid):
    system_uptime = float(Path("/proc/uptime").read_text().split()[0])
    raw = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    birth = int(raw[19])
    states = []
    for task in Path(f"/proc/{pid}/task").iterdir():
        states.append(task.joinpath("stat").read_text().rsplit(")", 1)[1].split()[0])
    global_states=subprocess.check_output(['ps','-eLo','stat='],text=True).splitlines()
    return {"pid": pid, "service_start_ticks": birth, "system_uptime_s": system_uptime,
            "uptime":subprocess.check_output(['uptime'],text=True).strip(),"system_rthreads":sum(s.strip().startswith('R') for s in global_states),
            "service_uptime_s": system_uptime - birth / os.sysconf("SC_CLK_TCK"),
            "rthreads": states.count("R"), "thread_states": {s: states.count(s) for s in sorted(set(states))}}

def command(endpoint, input_file, output, timeout):
    return [AIPERF, "profile", "--model", MODEL, "--endpoint-type", "chat", "--streaming", "--url", endpoint,
      "--input-file", str(input_file), "--custom-dataset-type", "single_turn", "--dataset-sampling-strategy", "sequential",
      "--request-count", "2", "--concurrency", "2", "--wait-for-model-timeout", "0", "--request-timeout-seconds", str(timeout),
      "--no-server-metrics", "--no-gpu-telemetry", "--ui", "none", "--tokenizer", "builtin", "--use-server-token-count",
      "--use-legacy-max-tokens", "--export-level", "raw", "--output-artifact-dir", str(output)]

def raw_summary(path, group):
    metric_path = Path(path).with_name("profile_export.jsonl")
    metric_rows = rows(metric_path)
    metrics_by_id = {x.get("metadata", {}).get("x_request_id"): x.get("metrics") for x in metric_rows}
    if len(metric_rows) != 2 or None in metrics_by_id or len(metrics_by_id) != 2:
        raise ValueError("metrics export must contain two unique request ids")
    output, expected = [], 256 if group == "X" else 128
    for row in rows(path):
        request_id = row.get("metadata", {}).get("x_request_id")
        payload, metrics = row["payload"], metrics_by_id.get(request_id)
        if row.get("status") != 200 or row.get("metadata", {}).get("was_cancelled") is not False:
            raise ValueError("raw receipt status/cancellation differs")
        if metrics is None: raise ValueError("raw request has no matching metrics request id")
        if payload.get("max_tokens") != expected or tuple(payload.get(k) for k in ("temperature", "top_p", "ignore_eos")) != (0, 1, False): raise ValueError("raw frozen parameters differ")
        finishes = []
        for response in row.get("responses", []):
            for packet in response.get("packets", []):
                try: chunk = json.loads(packet.get("value", "")) if packet.get("name") == "data" else {}
                except (TypeError, ValueError): chunk = {}
                finishes += [x.get("finish_reason") for x in chunk.get("choices", []) if x.get("finish_reason")]
        itl = metrics.get("inter_token_latency", {}).get("value"); completion = metrics.get("usage_completion_tokens", {}).get("value")
        prompt = metrics.get("usage_prompt_tokens", {}).get("value")
        if not isinstance(itl, (int, float)) or itl <= 0 or metrics.get("inter_token_latency", {}).get("unit") != "ms": raise ValueError("raw inter_token_latency unavailable")
        if not isinstance(completion, int): raise ValueError("raw completion token count unavailable")
        output.append({"request_id": request_id, "finish_reasons": finishes, "completion_tokens": completion,
          "prompt_tokens": prompt, "L_k_tokens": prompt / 1000 if isinstance(prompt, (int, float)) else None,
          "inter_token_latency_ms": itl, "per_lane_decode_tps": 1000 / itl})
    if len(output) != 2: raise ValueError("raw export must contain two responses")
    if group == "X" and not all(x["completion_tokens"] == 256 and "length" in x["finish_reasons"] for x in output): raise ValueError("X lower-7.8 anomaly: expected 256 length completions")
    if not all(x["per_lane_decode_tps"] >= 7.8 for x in output): raise ValueError(f"{group} lower-7.8 TPS anomaly")
    return output

def d0_delta(path, cursor):
    data = rows(path); new = data[cursor:]; steps = [x for x in new if x.get("bs") == 2]
    if not steps: raise ValueError("no new stock bs=2 D0 rows")
    missing = sum(x["missing_total"] for x in steps)
    active = sum(sum(x.get("active_per_layer", [])) for x in steps)
    value = {"from_index": cursor, "to_index": len(data), "stock_bs2_steps": len(steps), "rids": [x.get("rids") for x in steps],
      "batch_missing_total": missing, "m_equivalent_shared_batch_per_lane_average": missing / (len(steps) * 2 * 480),
      "attribution": "batch deduplicated misses; not independent UID m"}
    if active: value["dedup_real_miss_ratio"] = missing / active
    return value

def require(doc, phase):
    if doc.get("admit") is not True or doc.get("calls_per_phase") != 4 or doc.get("concurrency") != 2: raise ValueError("admission scope differs")
    if phase not in LIMITS or phase not in doc.get("phases", {}): raise ValueError("phase not admitted")
    for group in GROUPS:
        path = doc["inputs"][group]
        if sha(path) != doc.get("input_sha256", {}).get(group): raise ValueError(f"{group} input hash differs")
        check_inputs(path, group)
    if doc.get("runner_sha256") and doc["runner_sha256"] != sha(__file__): raise ValueError("runner source pin differs")

def run(doc, phase):
    require(doc, phase); phase_doc = doc["phases"][phase]; out = Path(doc["output_root"]) / phase; out.mkdir(parents=True, exist_ok=False)
    deadline = float(phase_doc["deadline_epoch_s"])
    if deadline <= time.time() or deadline - time.time() > LIMITS[phase]: raise ValueError("phase absolute deadline invalid")
    results = []
    for group in GROUPS:
        call = out / group; call.mkdir(); before = proc_snapshot(int(phase_doc["service_pid"]))
        if before["service_start_ticks"] != int(phase_doc["service_start_ticks"]): raise RuntimeError("service PID birth differs")
        (call/'before.json').write_text(json.dumps(before,indent=2))
        d0_file=Path(phase_doc.get('d0_path','')+'_decode_steps.jsonl')
        cursor = (len(rows(d0_file)) if d0_file.exists() else 0) if phase == "d0" else None
        argv = command(phase_doc["endpoint"], doc["inputs"][group], call, min(300, max(1, int(deadline - time.time()))))
        (call / "command.json").write_text(json.dumps(argv, indent=2)); result = None
        try: result = subprocess.run(argv, capture_output=True, text=True, timeout=max(1, deadline - time.time()))
        except subprocess.TimeoutExpired as exc: result = subprocess.CompletedProcess(argv, 124, exc.stdout or "", exc.stderr or "deadline expired")
        finally:
            if result is not None:
                (call / "exit.json").write_text(json.dumps({"returncode": result.returncode})); (call / "stdout.txt").write_text(result.stdout.decode(errors="replace") if isinstance(result.stdout, bytes) else result.stdout or ""); (call / "stderr.txt").write_text(result.stderr.decode(errors="replace") if isinstance(result.stderr, bytes) else result.stderr or "")
        after = proc_snapshot(int(phase_doc["service_pid"]))
        (call/'after.json').write_text(json.dumps(after,indent=2))
        if after["service_start_ticks"] != before["service_start_ticks"]: raise RuntimeError("service PID reuse detected")
        if result.returncode: raise RuntimeError(f"aiperf exit={result.returncode}")
        item = {"group": group, "before": before, "after": after, "raw": raw_summary(call / "profile_export_raw.jsonl", group)}
        if phase == "d0":
            until = time.monotonic() + 1
            while len(rows(phase_doc["d0_path"] + "_decode_steps.jsonl")) <= cursor and time.monotonic() < until: time.sleep(.05)
            item["d0"] = d0_delta(phase_doc["d0_path"] + "_decode_steps.jsonl", cursor)
        results.append(item)
    (out / "terminal.json").write_text(json.dumps({"status": "complete", "phase": phase, "generation_calls": 4, "results": results}, indent=2))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--run",action="store_true");p.add_argument("--phase",choices=LIMITS);p.add_argument("--admission",type=Path);a=p.parse_args()
    if not a.run: print("inert: --run --phase --admission required"); return
    if not a.phase or not a.admission: p.error("--run requires --phase and --admission")
    if a.admission.is_symlink() or a.admission.stat().st_mode&0o222:raise RuntimeError('read-only root admission required')
    doc = json.loads(a.admission.read_text())
    try: run(doc, a.phase)
    except Exception as exc:
        status = "not_met" if "anomaly" in str(exc) else "failed_harness"
        target = Path(doc.get("output_root", ".")) / a.phase
        if target.exists():
            (target / "terminal.json").write_text(json.dumps({"status":status, "phase":a.phase, "error":str(exc)}, indent=2))
        print(json.dumps({"status":status, "phase":a.phase, "error":str(exc)})); raise
if __name__ == "__main__": main()
