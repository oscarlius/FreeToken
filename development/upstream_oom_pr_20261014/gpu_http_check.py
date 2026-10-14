"""Fixed-count, private HTTP/native-ID validation for the OOM recovery port."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "upstream_layer_major_pr_20261014"))
import gpu_client

MODEL = "Qwen3.8-Flash-Next-NVFP4"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
gpu_client.MAX_DEADLINE_REQUEST_SECONDS = 600


def remaining(deadline: float) -> float:
    seconds = deadline - time.time()
    if seconds <= 0:
        raise TimeoutError("absolute measurement deadline exceeded")
    return seconds


def save(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)


def health(base: str, deadline: float) -> dict:
    with urllib.request.urlopen(base + "/health", timeout=min(5, remaining(deadline))) as response:
        return json.load(response)


def unique_value(value, key: str):
    found = []
    def walk(item):
        if isinstance(item, dict):
            if key in item:
                found.append(item[key])
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    if not found or any(item != found[0] for item in found):
        raise RuntimeError("missing or ambiguous health field: " + key)
    return found[0]


def start_ticks(pid: int) -> int | None:
    try:
        return int((Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19])
    except FileNotFoundError:
        return None


def fault_request(base: str, text: str, out: Path, deadline: float, result: dict) -> None:
    payload = {"model": MODEL, "prompt": text, "max_tokens": 128, "temperature": 0,
               "ignore_eos": True, "stream": True, "stream_options": {"include_usage": True}}
    request = urllib.request.Request(base + "/v1/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    result["started_unix_ns"] = time.time_ns()
    try:
        try:
            response = urllib.request.urlopen(request, timeout=min(600, remaining(deadline)))
        except urllib.error.HTTPError as error:
            response = error
        with response, (out / "fault_uid1.sse").open("xb") as handle:
            raw = response.read()
            handle.write(raw)
            result["http_status"] = response.code
        result["explicit_oom_terminal"] = b"insufficient_workspace" in raw and b"worker_restarting_after_cuda_oom" in raw
        if not result["explicit_oom_terminal"]:
            raise RuntimeError("fault request did not receive the expected explicit OOM terminal")
        result["ok"] = True
    except BaseException as error:
        result.update(ok=False, error=repr(error))
    finally:
        result["finished_unix_ns"] = time.time_ns()


def run(args) -> dict:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = json.loads(Path(args.inputs).read_text())
    native = out / "native"
    calls = 0
    def good(name: str, text: str, count: int) -> dict:
        nonlocal calls
        calls += 1
        receipt = gpu_client.invoke(args.base_url, MODEL, text, name, out, native_dir=native,
                                    deadline_unix=args.deadline_unix)
        gpu_client._validate_terminal(receipt, name, count)
        if receipt["native_cached_tokens"] != 0:
            raise RuntimeError("cold validation request unexpectedly reused cached tokens: " + name)
        return receipt

    initial = health(args.base_url, args.deadline_unix)
    if args.arm != "candidate_on":
        good("warmup512", inputs["warmup512"], 512)
        short = good("short512", inputs["short512"], 512)
        long = good("long8257", inputs["long8257"], 8257)
        return {"classification": "kept", "calls": calls,
                "refs": {"short512": short["native_token_ids"], "long8257": long["native_token_ids"]}}

    short = good("short512", inputs["short512"], 512)
    calls += 1
    fault = {}
    thread = threading.Thread(target=fault_request,
        args=(args.base_url, inputs["long8257"], out, args.deadline_unix, fault), daemon=True)
    thread.start()
    try:
        poll_deadline = min(args.deadline_unix, time.time() + 90)
        while True:
            restarting = health(args.base_url, poll_deadline)
            if restarting.get("maintenance") == "restarting":
                if unique_value(restarting, "backend_epoch") != 1:
                    raise RuntimeError("unexpected replacement epoch")
                break
            if fault.get("ok") is False:
                raise RuntimeError("fault request failed: " + str(fault))
            if restarting.get("status") == "error":
                raise RuntimeError("recovery failed before admission")
            time.sleep(min(.1, remaining(poll_deadline)))
        save(out / "health_restarting.json", restarting)
        queued_started = time.time_ns()
        queued = good("queued512", inputs["short512"], 512)
        if queued["native_token_ids"] != short["native_token_ids"]:
            raise RuntimeError("not_met: queued output differs from fresh initial reference")
        recovered = health(args.base_url, args.deadline_unix)
        if recovered.get("maintenance") != "serving" or unique_value(recovered, "backend_epoch") != 1:
            raise RuntimeError("replacement did not become serving")
        if unique_value(initial, "instance_id") != unique_value(recovered, "instance_id"):
            raise RuntimeError("API identity changed across recovery")
        save(out / "health_recovered.json", recovered)
        thread.join(timeout=min(10, remaining(args.deadline_unix)))
        if thread.is_alive() or not fault.get("ok"):
            raise RuntimeError("fault stream did not terminate explicitly: " + str(fault))
        save(out / "fault_terminal.json", fault)
        faults = [json.loads(line) for line in (native / "oom_faults.jsonl").read_text().splitlines()]
        actual = [row for row in faults if row.get("event") == "actual_exception"
                  and row.get("type") in {"OutOfMemoryError", "torch.cuda.OutOfMemoryError"}]
        if len(actual) != 1 or actual[0]["epoch"] != 0 or actual[0]["uid"] != 1:
            raise RuntimeError("actual CUDA OOM evidence missing or not uniquely bound")
        handles = [json.loads(line) for line in (native / "backend_handles.jsonl").read_text().splitlines()]
        if len(handles) != 2 or [row["epoch"] for row in handles] != [0, 1]:
            raise RuntimeError("backend factory generation ledger differs")
        for generation in handles:
            if not isinstance(generation.get("api_start_ticks"), int) or generation["api_start_ticks"] <= 0:
                raise RuntimeError("API birth identity was not captured")
            if not generation.get("workers"):
                raise RuntimeError("worker generation is empty")
            for worker in generation["workers"]:
                if not isinstance(worker.get("pid"), int) or not isinstance(worker.get("start_ticks"), int) or worker["start_ticks"] <= 0:
                    raise RuntimeError("worker birth identity was not captured")
        if handles[0]["api_pid"] != handles[1]["api_pid"] or handles[0]["api_start_ticks"] != handles[1]["api_start_ticks"]:
            raise RuntimeError("API process identity changed")
        if any(start_ticks(row["pid"]) == row["start_ticks"] for row in handles[0]["workers"]):
            raise RuntimeError("retired backend worker still exists")
        if any(start_ticks(row["pid"]) != row["start_ticks"] for row in handles[1]["workers"]):
            raise RuntimeError("replacement worker identity changed")
        long = good("long8257", inputs["long8257"], 8257)
        with urllib.request.urlopen(args.base_url + "/v1/stats", timeout=min(5, remaining(args.deadline_unix))) as response:
            final_stats = json.load(response)
        if final_stats["requests"]["active"] != 0 or final_stats["requests"]["completed"] != 4:
            raise RuntimeError("OOM recovery left incorrect request accounting")
        save(out / "stats_after_recovery.json", final_stats)
        return {"classification": "kept", "calls": calls, "fault": fault,
                "queued_started_unix_ns": queued_started, "actual_cuda_oom": actual,
                "backend_handles": handles, "refs": {"short512": short["native_token_ids"], "long8257": long["native_token_ids"]}}
    finally:
        thread.join(timeout=min(2, max(0, args.deadline_unix - time.time())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("main", "candidate_off", "candidate_on"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--deadline-unix", type=float, required=True)
    parser.add_argument("--inputs", required=True)
    arguments = parser.parse_args()
    try:
        summary = run(arguments)
    except BaseException as error:
        Path(arguments.out).mkdir(parents=True, exist_ok=True)
        save(Path(arguments.out) / "SUMMARY.json", {"classification": "not_met" if "not_met:" in str(error) else "failed_harness", "error": repr(error)})
        raise
    save(Path(arguments.out) / "SUMMARY.json", summary)
