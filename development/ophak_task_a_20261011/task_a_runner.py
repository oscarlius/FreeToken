#!/usr/bin/env python3
"""op-hak 任务 A 工装：锚点切段开/关，真实轨迹逐轮首 token 测量（只测量，不判定）。

命令（在 WORK 目录下运行，服务器上用 venv 的 python）：
  rehearse --run-dir DIR [--port P] [--scale S] [--inject-json JSON]
      CPU 演练：桩服务代替 ft serve，走同一条窗口编排、请求与日志解析路径。不占 GPU，不碰 8095。
  w0-check
      只读检查 W0 开窗条件，结果写入 WORK/W0_CHECK.json（W3 停服之前执行）。
  window --run-dir DIR
      真实 W4 窗口（4 个服务）。需要 W0_CHECK.json 通过且 481 已按 W3 停止。P2 才可执行。

本文件不写判读结论。判读由 analyze_task_a.py 按预登记机械计算。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

WORK = Path(__file__).resolve().parent
INPUTS_JSON = WORK / "INPUTS.json"
W0_RESULT = WORK / "W0_CHECK.json"
PREREG_PATH = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_A.json")
PREREG_SHA256 = "0e1708bf033f26ec5f5cde94a1cd3ff86e786c854990033df8246a04006814b9"
PRODUCTION_ACTIVE = Path("/data2/FreeToken/run/production.active.json")
PRODUCTION_STOPPED = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-10/stopped.json")
PRODUCTION_ENDPOINT = "http://172.16.108.9:8095"
COORD_LOG = Path("/data2/FreeToken/plan/COORDINATION_LOG.md")
TASK_A_STOP = Path("/data2/FreeToken/plan/OPHAK_TASK_A_STOP.md")
GPU_LOCK = Path("/data2/_shared/gpu.lock")
D09_DIR = "/data2/FreeToken/development/gemini_d09_enable_20261011"
OH_WINDOW_PATH = Path("/data2/FreeToken/development/gemini_oom_hybrid_20261011/oh_window.py")
RELEASE_PYTHONPATH = "/data2/FreeToken/wt/release-e2/python"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
SERVE_HOST = "127.0.0.1"
SERVE_PORT = 8123
SERVICES: tuple[tuple[str, str], ...] = (("A1_on", "on"), ("B1_off", "off"), ("B2_off", "off"), ("A2_on", "on"))
WINDOW_LIMIT_S = 3600.0          # W4：总时限 60 分钟
SERVICE_RESERVE_S = 480.0        # 每个服务约 7–8 分钟；剩余不足则不开新服务（§5 超时路由）
READY_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 600.0
BETWEEN_REQUESTS_S = 1.0         # §2.2：前一条收到 usage 后，至少间隔 1 秒
SETTLE_LOG_S = 0.3               # 请求结束后等 serve.log 刷盘
W0_MAX_AGE_S = 2700.0
PREFILL_LINE_RE = re.compile(r"Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)")
RELEASE_LINE_RE = re.compile(r"^- \S+ 主会话.*任务 A 放行")
OOM_MARKERS = ("out of memory", "worker_restarting_after_oom")

# ---- 任务 A2（续篇，见 plan/OPHAK_TASK_A2_T2_ONLY_20261011.md）
A2_RELEASE_LINE_RE = re.compile(r"^- \S+ 主会话.*任务 A2 放行")
A2_READY_LINE_RE = re.compile(r"^- \S+ op-hak：任务 A2 P1 就绪")
WATCH_POLL_S = 5.0          # §3.2：请求进行中每 5 秒检查一次 serve.log（判定）与 /health（只记录，不作判据）
OOM_TEXT_RE = re.compile(r"out of memory", re.IGNORECASE)  # 原文：RuntimeError: Triton Error [CUDA]: out of memory
WORKER_MARKER_RE = re.compile(r"backend worker \S+ exited|backend worker is gone", re.IGNORECASE)
# 原文：Backend supervisor: backend worker freetoken-TP0-scheduler exited / Backend worker is gone and cannot be restarted
RESTORE11_STOPPED = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11/stopped.json")
W0_RESULT_A2 = WORK / "W0_CHECK_A2.json"
# 两套战役的参数。a1 为历史（已完成，不可再用于开窗）；a2 为续篇，总时限 45 分钟，保留 6 分钟，只跑 T2。
CAMPAIGNS: dict[str, dict[str, Any]] = {
    "a1": {"trajectories": ("seed_real", "T2"), "limit_s": WINDOW_LIMIT_S, "reserve_s": SERVICE_RESERVE_S,
           "approval": "RESTORE481-MORNING-20261011-10", "release_re": RELEASE_LINE_RE,
           "stopped": PRODUCTION_STOPPED, "w0_result": W0_RESULT},
    "a2": {"trajectories": ("T2",), "limit_s": 2700.0, "reserve_s": 360.0,
           "approval": "RESTORE481-MORNING-20261011-11", "release_re": A2_RELEASE_LINE_RE,
           "stopped": RESTORE11_STOPPED, "w0_result": W0_RESULT_A2},
}
D11P0_RUNS_ROOT = Path("/data2/FreeToken/runs")
D11P0_QUIET_S = 600.0  # 补充 1 第 3 节：runs 下名称含 d11_p0 的目录，最近 10 分钟内有文件更新即视为 D11-P0 仍在运行


class RunnerError(RuntimeError):
    """指令没有覆盖的情况，或前置条件不满足。"""


class LaunchError(RuntimeError):
    """服务没有起来，或 argv 门不通过。"""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def messages_sha256(messages: list[dict]) -> str:
    """与 freeze_inputs.py 相同的规范化哈希：桩服务用它把请求映射回轮次。"""
    return sha256_hex(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def server_now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def write_new(path: Path, obj: Any) -> None:
    """只新建，不覆盖：证据文件一旦写出就不改。"""
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    path.chmod(0o444)


def is_oom_error(error: dict) -> bool:
    """与 oh_window.check_is_oom_chunk 的判定规则相同。"""
    message = str(error.get("message", "")).lower()
    return any(marker in message for marker in OOM_MARKERS)


def load_prereg() -> dict:
    data = PREREG_PATH.read_bytes()
    if sha256_hex(data) != PREREG_SHA256:
        raise RunnerError(f"预登记 SHA 不符：{sha256_hex(data)}")
    return json.loads(data)


def load_inputs() -> dict:
    return json.loads(INPUTS_JSON.read_bytes())


# ---------------------------------------------------------------- 请求计划（§2.2，顺序固定）

def plan_item(key: str, rec: dict, expect: dict | None) -> dict:
    body = (WORK / rec["file"]).read_bytes()
    if sha256_hex(body) != rec["sha256"]:
        raise RunnerError(f"输入文件已被改动：{rec['file']}")
    payload = json.loads(body)
    msg_sha = messages_sha256(payload["messages"])
    if msg_sha != rec["messages_sha256"]:
        raise RunnerError(f"messages 哈希与冻结记录不符：{rec['file']}")
    return {"key": key, "trajectory": key.split("/")[0], "round": int(key.split("/")[1]),
            "file": rec["file"], "body": body, "payload_sha256": rec["sha256"],
            "messages_sha256": msg_sha, "expect": expect}


def build_plan(inputs: dict, prereg: dict, arm: str,
               trajectories: tuple[str, ...] = ("seed_real", "T2")) -> list[dict]:
    """warmup，然后所选轨迹的轮次（默认 seed_real 第 0–7 轮，再 T2 第 0–11 轮）。不得调换。
    A2 只跑 T2：trajectories=("T2",)。"""
    if arm not in ("on", "off"):
        raise RunnerError(f"未知臂：{arm}")
    if not trajectories or any(t not in ("seed_real", "T2") for t in trajectories):
        raise RunnerError(f"未知轨迹：{trajectories}")
    items = [plan_item("warm/00", inputs["warmup"], None)]
    for row in inputs["rounds"]:
        if row["trajectory"] not in trajectories:
            continue
        exp = prereg["trajectories"][row["trajectory"]]["rounds"][row["round"]]
        expect = {"prompt_tokens": exp["prompt_tokens"], "cached": exp["cached"], "class": exp["class"],
                  "segments": exp["on_segments"] if arm == "on" else exp["off_segments"]}
        items.append(plan_item(f'{row["trajectory"]}/{row["round"]:02d}', row, expect))
    return items


# ---------------------------------------------------------------- SSE 解析与单请求

def absorb_chunk(outcome: dict, chunk: dict, elapsed_s: float) -> bool:
    """处理一个 SSE 数据包，返回 True 表示应停止读取。

    首 token 只认非空的 reasoning_content 或 content。第一个 role 包的 content 是空串，不能计时。
    tool_calls 单独记录，不作为首 token。
    """
    if chunk.get("error"):
        is_oom = is_oom_error(chunk["error"])
        outcome["status"] = "oom" if is_oom else "error"
        outcome["oom_message"] = chunk["error"].get("message") if is_oom else None
        outcome["error"] = json.dumps(chunk["error"], ensure_ascii=False)[:500]
        return True
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        reasoning = delta.get("reasoning_content")
        content = delta.get("content")
        tool_calls = delta.get("tool_calls")
        if outcome["ttft_s"] is None:
            if reasoning:
                outcome["ttft_s"], outcome["ttft_source"] = elapsed_s, "reasoning_content"
            elif content:
                outcome["ttft_s"], outcome["ttft_source"] = elapsed_s, "content"
        if tool_calls and outcome["tool_call_first_s"] is None:
            outcome["tool_call_first_s"] = elapsed_s
        for piece in (reasoning, content):
            if piece:
                outcome["_parts"].append(piece)
        if tool_calls:
            outcome["_parts"].append(json.dumps(tool_calls, ensure_ascii=False, sort_keys=True))
        if choice.get("finish_reason"):
            outcome["finish_reason"] = choice["finish_reason"]
    usage = chunk.get("usage")
    if usage:
        details = usage.get("prompt_tokens_details") or {}
        outcome["usage"] = {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cached_tokens": int(details.get("cached_tokens") or 0),
        }
    return False


def post_chat(endpoint: str, body: bytes, *, transport: httpx.BaseTransport | None = None,
              timeout_s: float = REQUEST_TIMEOUT_S, clock: Callable[[], float] = time.perf_counter,
              _holder: dict | None = None) -> dict:
    """发送一条流式请求。httpx 直连，不绕代理，不重试。_holder 用于让监视线程拿到客户端句柄（A2 主动断开）。"""
    outcome: dict[str, Any] = {"status": "ok", "http_status": None, "ttft_s": None, "ttft_source": None,
                               "tool_call_first_s": None, "usage": None, "finish_reason": None,
                               "error": None, "oom_message": None, "_parts": []}
    kwargs: dict[str, Any] = {"trust_env": False, "timeout": timeout_s}
    if transport is not None:
        kwargs["transport"] = transport
    t0 = clock()
    try:
        with httpx.Client(**kwargs) as client:
            if _holder is not None:
                _holder["client"] = client
            with client.stream("POST", f"{endpoint}/v1/chat/completions", content=body,
                               headers={"content-type": "application/json"}) as resp:
                outcome["http_status"] = resp.status_code
                if resp.status_code != 200:
                    outcome["status"] = "http_error"
                    outcome["error"] = resp.read().decode("utf-8", "replace")[:500]
                else:
                    for line in resp.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        if absorb_chunk(outcome, json.loads(data), clock() - t0):
                            break
    except httpx.TimeoutException as exc:
        outcome["status"], outcome["error"] = "timeout", repr(exc)
    except httpx.TransportError as exc:
        outcome["status"], outcome["error"] = "transport_error", repr(exc)
    except ValueError as exc:
        outcome["status"], outcome["error"] = "bad_sse", repr(exc)
    outcome["total_s"] = clock() - t0
    text = "".join(outcome.pop("_parts"))
    outcome["output_text"] = text
    outcome["output_chars"] = len(text)
    outcome["output_sha256"] = sha256_hex(text.encode("utf-8"))
    if outcome["status"] == "ok" and outcome["usage"] is None:
        outcome["status"] = "no_usage"
    return outcome


def sample_gpu_memory() -> int | None:
    """nvidia-smi 读取 GPU 已用显存（MiB）。失败返回 None。只记录，不作判据（A2 §2.3）。"""
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                      text=True, timeout=15)
        return int(out.strip().splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


MEMORY_SAMPLER: Callable[[], int | None] = sample_gpu_memory


def default_health_get(endpoint: str) -> dict:
    with httpx.Client(trust_env=False, timeout=3.0) as client:
        return client.get(f"{endpoint}/health").json()


class WorkerWatch:
    """请求进行中的 worker 退出监视（A2 §3.2）。判定只看 serve.log 的标记：scan_new_log 只看 offset 之后的新增内容。
    /health 每次轮询都查一次，只记录连续失败次数与最后状态，不作判据（2026-10-11，freetoken-06 答复 2：选项 b）。"""

    def __init__(self, endpoint: str, serve_log: Path, offset: int,
                 *, health_get: Callable[[str], dict] | None = None) -> None:
        self.endpoint = endpoint
        self.serve_log = serve_log
        self.offset = offset
        self.health_get = health_get or default_health_get
        self.health_failures = 0              # 当前连续失败次数（成功即清零）
        self.health_failures_max = 0          # 本请求内连续失败次数的最大值
        self.health_last: str | None = None   # 最后一次结果："ok"、"status:<值>" 或 "error:<异常类名>"
        self.polls = 0

    def scan_new_log(self) -> str | None:
        with self.serve_log.open("rb") as handle:
            handle.seek(self.offset)
            new = handle.read().decode("utf-8", "replace")
            self.offset = handle.tell()
        if OOM_TEXT_RE.search(new):
            return "oom"
        if WORKER_MARKER_RE.search(new):
            return "worker_exit"
        return None

    def check_health(self) -> None:
        """只记录，不判定。"""
        try:
            doc = self.health_get(self.endpoint)
            status = doc.get("status") if isinstance(doc, dict) else None
            healthy = status == "ok"
            self.health_last = "ok" if healthy else f"status:{status}"
        except (httpx.HTTPError, ValueError) as exc:
            healthy = False
            self.health_last = f"error:{type(exc).__name__}"
        if healthy:
            self.health_failures = 0
            return
        self.health_failures += 1
        self.health_failures_max = max(self.health_failures_max, self.health_failures)

    def poll(self) -> str | None:
        self.polls += 1
        trip = self.scan_new_log()
        if trip:
            return trip
        self.check_health()
        return None


def post_chat_watched(endpoint: str, body: bytes, serve_log: Path, *, transport: httpx.BaseTransport | None = None,
                      timeout_s: float = REQUEST_TIMEOUT_S, clock: Callable[[], float] = time.perf_counter,
                      poll_s: float | None = None, health_get: Callable[[str], dict] | None = None) -> dict:
    """请求进行中每 poll_s 秒检查一次 serve.log（判定）与 /health（只记录，不作判据）。命中标记即主动断开并返回；服务进程由清场结束。
    请求结束后再扫一次 serve.log：客户端先看到连接错误、而标记还没被轮询到的情况，也记为 worker_exit（消除竞态）。"""
    interval = WATCH_POLL_S if poll_s is None else poll_s
    watch = WorkerWatch(endpoint, serve_log, serve_log.stat().st_size, health_get=health_get)
    box: dict[str, Any] = {}
    holder: dict[str, Any] = {}

    def run() -> None:
        box["outcome"] = post_chat(endpoint, body, transport=transport, timeout_s=timeout_s, clock=clock,
                                   _holder=holder)

    t0 = clock()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    trip: str | None = None
    while thread.is_alive():
        thread.join(timeout=interval)
        if not thread.is_alive():
            break
        trip = watch.poll()
        if trip:
            break
    detected_wall: float | None = None
    if trip:
        client = holder.get("client")
        if client is not None:
            client.close()  # 主动断开连接；服务进程随后由清场结束，连接随之关闭
        detected_wall = time.time()
        outcome: dict[str, Any] = {
            "status": trip, "http_status": None, "ttft_s": None, "ttft_source": None,
            "tool_call_first_s": None, "usage": None, "finish_reason": None, "oom_message": None,
            "error": f"{trip}：请求进行中由监视线程检测到，工装主动断开", "total_s": clock() - t0,
            "output_text": "", "output_chars": 0, "output_sha256": sha256_hex(b""),
        }
    else:
        outcome = box.get("outcome") or {
            "status": "runner_exception", "error": "请求线程异常结束", "usage": None, "total_s": clock() - t0,
            "output_text": "", "output_chars": 0, "output_sha256": sha256_hex(b""),
            "http_status": None, "ttft_s": None, "ttft_source": None, "tool_call_first_s": None,
            "finish_reason": None, "oom_message": None}
        final = watch.scan_new_log()
        if final and outcome["status"] in ("transport_error", "timeout", "bad_sse", "no_usage", "error", "http_error"):
            trip = final
            detected_wall = time.time()
            outcome["error"] = f"{final}：请求结束后在 serve.log 中检测到（原记录 {outcome['status']}）"
            outcome["status"] = final
    outcome["watch_trip"] = trip
    outcome["watch_polls"] = watch.polls
    outcome["health_failures_max"] = watch.health_failures_max
    outcome["health_last"] = watch.health_last
    outcome["trip_wall_time"] = detected_wall
    return outcome


def read_prefill_lines(path: Path, offset: int) -> list[dict]:
    with path.open("rb") as handle:
        handle.seek(offset)
        text = handle.read().decode("utf-8", "replace")
    return [{"new_seq": int(a), "new_token": int(b), "cached_token": int(c)}
            for a, b, c in PREFILL_LINE_RE.findall(text)]


def run_request(endpoint: str, item: dict, serve_log: Path, *, transport=None,
                sleep: Callable[[float], None] = time.sleep, watch: bool = True,
                health_get: Callable[[str], dict] | None = None) -> tuple[dict, str]:
    """发送一条计划内的请求。watch=True 时请求进行中监视 worker 退出（A2）；每条请求前后各采一次显存。"""
    offset = serve_log.stat().st_size
    memory_before = MEMORY_SAMPLER()
    if watch:
        outcome = post_chat_watched(endpoint, item["body"], serve_log, transport=transport, health_get=health_get)
    else:
        outcome = post_chat(endpoint, item["body"], transport=transport)
    memory_after = MEMORY_SAMPLER()
    sleep(SETTLE_LOG_S)
    text = outcome.pop("output_text")
    record = {
        "key": item["key"], "trajectory": item["trajectory"], "round": item["round"],
        "payload_file": item["file"], "payload_sha256": item["payload_sha256"],
        "messages_sha256": item["messages_sha256"], "expect": item["expect"],
        "memory_before_mib": memory_before, "memory_after_mib": memory_after,
        "prefill_lines": read_prefill_lines(serve_log, offset),
    }
    record.update(outcome)
    return record, text


def excerpt_oom(serve_log: Path, out: Path, context: int = 40) -> None:
    lines = serve_log.read_text(encoding="utf-8", errors="replace").splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if any(marker in line.lower() for marker in ("out of memory", "outofmemory", "worker_restarting",
                                                     "backend worker")):
            keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    with out.open("x", encoding="utf-8", newline="\n") as handle:
        for i in sorted(keep):
            handle.write(lines[i] + "\n")


def run_service(endpoint: str, name: str, arm: str, serve_log: Path, out_dir: Path, plan: list[dict], *,
                transport=None, sleep: Callable[[float], None] = time.sleep,
                between_s: float = BETWEEN_REQUESTS_S) -> dict:
    """按计划逐条发送。OOM：立即中止本服务，不重试（§5）。其它请求错误：停止本服务并上报（指令未覆盖）。"""
    summary: dict[str, Any] = {"service": name, "arm": arm, "planned": len(plan), "done": 0,
                               "status": "complete", "stop_reason": None}
    outputs: dict[str, str] = {}
    with (out_dir / "requests.jsonl").open("x", encoding="utf-8", newline="\n") as records:
        for item in plan:
            record, text = run_request(endpoint, item, serve_log, transport=transport, sleep=sleep)
            records.write(json.dumps(record, ensure_ascii=False) + "\n")
            records.flush()
            outputs[item["key"]] = text
            if record["status"] in ("oom", "worker_exit"):
                # OOM 与 worker 退出：中止本服务，不重试，窗口继续下一个服务（A2 §3.2）
                summary.update(status=record["status"],
                               stop_reason=record.get("oom_message") or record["error"])
                break
            if record["status"] != "ok":
                summary.update(status="request_error", stop_reason=f'{record["status"]}: {record["error"]}')
                break
            summary["done"] += 1
            sleep(between_s)
    write_new(out_dir / "outputs.json", outputs)
    if summary["status"] in ("oom", "worker_exit"):
        excerpt_oom(serve_log, out_dir / "oom_excerpt.log")
    write_new(out_dir / "summary.json", summary)
    return summary


# ---------------------------------------------------------------- argv 门与环境（W4 真实路径）

def build_argv(baseline: list[str], arm: str) -> tuple[list[str], list[dict]]:
    """A 臂：生产 argv 只改 host 与 port。B 臂：再追加 --no-prefill-anchor-cut。其它差异一律拒绝。"""
    if baseline[:3] != ["taskset", "-c", "1,3-47"]:
        raise LaunchError("生产 argv 的绑核前缀与预期不同")
    expected = list(baseline)
    for flag, value in (("--host", SERVE_HOST), ("--port", str(SERVE_PORT))):
        if expected.count(flag) != 1:
            raise LaunchError(f"生产 argv 中 {flag} 出现次数不是 1")
        expected[expected.index(flag) + 1] = value
    extra = [] if arm == "on" else ["--no-prefill-anchor-cut"]
    expected += extra
    diff = [{"index": i, "baseline": a, "actual": b} for i, (a, b) in enumerate(zip(baseline, expected)) if a != b]
    diff += [{"index": len(baseline) + j, "baseline": None, "actual": t} for j, t in enumerate(extra)]
    return expected, diff


def verify_argv(baseline: list[str], actual: list[str], arm: str) -> list[dict]:
    expected, diff = build_argv(baseline, arm)
    if actual != expected:
        raise LaunchError(f"argv 与允许的差异不符（臂 {arm}）")
    return diff


def clean_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in [k for k in env if k.startswith(("FT_", "FREETOKEN_"))]:
        del env[key]
    env.update({"PYTHONPATH": RELEASE_PYTHONPATH, "MASTER_PORT": "8096",
                "CUDA_VISIBLE_DEVICES": "0", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def wait_ready(endpoint: str, *, timeout_s: float, sleep: Callable[[float], None] = time.sleep,
               clock: Callable[[], float] = time.monotonic) -> bool:
    t0 = clock()
    with httpx.Client(trust_env=False, timeout=2.0) as client:
        while clock() - t0 < timeout_s:
            sleep(1.0)
            try:
                doc = client.get(f"{endpoint}/health").json()
            except (httpx.HTTPError, ValueError):
                continue
            if doc.get("status") == "ok" and doc.get("maintenance") == "serving":
                return True
    return False


class Handle:
    def __init__(self, name: str, arm: str, endpoint: str, serve_log: Path, out_dir: Path,
                 *, proc: subprocess.Popen, ready: bool, birth: Any = None, owner: Any = None,
                 log_handle: Any = None) -> None:
        self.name, self.arm, self.endpoint = name, arm, endpoint
        self.serve_log, self.out_dir = serve_log, out_dir
        self.proc, self.ready = proc, ready
        self.birth, self.owner, self.log_handle = birth, owner, log_handle


class StubLauncher:
    """P1 演练用：桩服务代替 ft serve。不取 GPU 锁，不碰 8095。"""

    def __init__(self, port: int, scale: float, inject: dict[str, dict[str, str]]) -> None:
        self.port, self.scale, self.inject = port, scale, inject

    def start(self, name: str, arm: str, out_dir: Path) -> Handle:
        out_dir.mkdir(parents=True, exist_ok=False)
        serve_log = out_dir / "serve.log"
        serve_log.touch()
        args = [sys.executable, "-B", str(WORK / "stub_server.py"), "--port", str(self.port),
                "--arm", arm, "--serve-log", str(serve_log), "--stats-out", str(out_dir / "stub_stats.jsonl"),
                "--inputs", str(INPUTS_JSON), "--prereg", str(PREREG_PATH), "--scale", str(self.scale)]
        for flag, value in self.inject.get(name, {}).items():
            args += [f"--{flag}", value]
        with (out_dir / "stub_stdout.log").open("wb") as stdout:
            proc = subprocess.Popen(args, cwd=str(out_dir), stdout=stdout, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        endpoint = f"http://{SERVE_HOST}:{self.port}"
        ready = wait_ready(endpoint, timeout_s=READY_TIMEOUT_S)
        return Handle(name, arm, endpoint, serve_log, out_dir, proc=proc, ready=ready)

    def stop(self, handle: Handle) -> bool:
        try:
            os.killpg(handle.proc.pid, signal.SIGTERM)
            handle.proc.wait(timeout=20)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(handle.proc.pid, signal.SIGKILL)
                handle.proc.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                return False
        return True


class RealLauncher:
    """W4 真实启动路径。argv、GPU 锁、启动、清理全部复用 oh_window 与 hybrid_service 的函数（只 import）。"""

    def __init__(self, baseline_argv: list[str]) -> None:
        self.baseline = baseline_argv
        spec = importlib.util.spec_from_file_location("oh_window", OH_WINDOW_PATH)
        self.oh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.oh)
        self.d07 = self.oh.load_d07()

    def start(self, name: str, arm: str, out_dir: Path) -> Handle:
        argv, diff = build_argv(self.baseline, arm)
        extra = [] if arm == "on" else ["--no-prefill-anchor-cut"]
        if self.oh.compute_expected_argv(self.baseline, {"type": "offload", "extra_argv": extra},
                                         host=SERVE_HOST, port=SERVE_PORT) != argv:
            raise LaunchError("oh_window 的 argv 计算与本工装不一致，停止")
        out_dir.mkdir(parents=True, exist_ok=False)
        write_new(out_dir / "argv_diff.json", {"arm": arm, "argv": argv, "diff": diff})
        try:
            self.oh.idle(self.d07, [(SERVE_HOST, SERVE_PORT)])
        except Exception as exc:  # noqa: BLE001 - 任何非空闲状态都是启动前失败
            raise LaunchError(f"启动前检查不通过：{exc!r}") from exc
        owner = self.d07.take_d07_gpu_lock(f"OPHAK-TASKA-20261011-{name}", 0)
        serve_log = out_dir / "serve.log"
        log_handle = serve_log.open("xb")
        try:
            proc = subprocess.Popen(argv, cwd=str(out_dir), env=clean_env(), stdout=log_handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            log_handle.close()
            self.d07.release_d07_gpu_lock(owner)
            raise LaunchError(f"spawn failed: {exc!r}") from exc
        birth = self.oh.capture_birth(proc, self.d07)
        endpoint = f"http://{SERVE_HOST}:{SERVE_PORT}"
        ready = wait_ready(endpoint, timeout_s=READY_TIMEOUT_S)
        return Handle(name, arm, endpoint, serve_log, out_dir, proc=proc, ready=ready,
                      birth=birth, owner=owner, log_handle=log_handle)

    def stop(self, handle: Handle) -> bool:
        ok = self.oh.cleanup(handle.proc, handle.birth, self.d07, handle.out_dir,
                             [(SERVE_HOST, SERVE_PORT)])
        handle.log_handle.close()
        if ok:
            self.d07.release_d07_gpu_lock(handle.owner)
        return ok


# ---------------------------------------------------------------- 窗口编排

def run_window(launcher: Any, services: tuple[tuple[str, str], ...], out_dir: Path,
               plan_for_arm: Callable[[str], list[dict]], *, transport=None,
               sleep: Callable[[float], None] = time.sleep, between_s: float = BETWEEN_REQUESTS_S,
               clock: Callable[[], float] = time.monotonic, limit_s: float = WINDOW_LIMIT_S,
               reserve_s: float = SERVICE_RESERVE_S) -> dict:
    """按固定顺序跑服务。OOM 只中止该服务（继续下一个）。清理失败、请求错误、工装异常都停止整个窗口。"""
    out_dir.mkdir(parents=True, exist_ok=False)
    started = clock()
    summary: dict[str, Any] = {"schema": "ophak_task_a_window/v1", "started_at": server_now(),
                               "services": [], "terminal": None}
    for name, arm in services:
        if limit_s - (clock() - started) < reserve_s:
            summary["terminal"] = "time_limit"
            break
        try:
            handle = launcher.start(name, arm, out_dir / name)
        except LaunchError as exc:
            summary["services"].append({"service": name, "arm": arm, "status": "launch_failed",
                                        "stop_reason": str(exc)})
            continue
        result: dict[str, Any]
        try:
            if handle.ready:
                # §2.3：服务就绪时也采一次显存（只记录）
                write_new(handle.out_dir / "memory_ready.json",
                          {"memory_used_mib": MEMORY_SAMPLER(), "sampled_at": server_now()})
                result = run_service(handle.endpoint, name, arm, handle.serve_log, handle.out_dir,
                                     plan_for_arm(arm), transport=transport, sleep=sleep, between_s=between_s)
            else:
                result = {"service": name, "arm": arm, "status": "launch_failed", "stop_reason": "ready timeout"}
        except Exception as exc:  # noqa: BLE001 - 工装异常：记录后清场并停止窗口
            result = {"service": name, "arm": arm, "status": "runner_exception", "stop_reason": repr(exc)}
        finally:
            cleaned = launcher.stop(handle)
        result["cleanup_ok"] = cleaned
        summary["services"].append(result)
        if not cleaned:
            (out_dir / "CLEANUP_BLOCKED.md").write_text(
                f"清理失败：{name}。GPU 锁未释放，窗口中止，需要主会话处理。\n", encoding="utf-8")
            summary["terminal"] = "cleanup_blocked"
            break
        if result["status"] in ("request_error", "runner_exception"):
            summary["terminal"] = result["status"]
            break
    if summary["terminal"] is None:
        summary["terminal"] = "complete"
    summary["finished_at"] = server_now()
    write_new(out_dir / "window_summary.json", summary)
    return summary


# ---------------------------------------------------------------- W0 与窗口前检查（只读）

def procs_matching(pred: Callable[[list[str], str], bool]) -> list[int]:
    me = {os.getpid()}
    out = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in me:
            continue
        try:
            argv = [a.decode(errors="replace") for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
            cwd = os.readlink(entry / "cwd")
        except OSError:
            continue
        if argv and pred(argv, cwd):
            out.append(int(entry.name))
    return sorted(out)


def production_health() -> dict:
    try:
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            return client.get(f"{PRODUCTION_ENDPOINT}/health").json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "unreachable", "error": repr(exc)}


def latest_mtime(path: Path) -> float:
    newest = path.stat().st_mtime
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                newest = max(newest, Path(root, name).stat().st_mtime)
            except OSError:
                continue
    return newest


def active_d11p0_dirs(runs_root: Path = D11P0_RUNS_ROOT, now: float | None = None,
                      quiet_s: float = D11P0_QUIET_S) -> list[dict]:
    """runs 下名称含 d11_p0 的顶层目录；最近 quiet_s 秒内有更新的视为活跃。没有这类目录则返回空列表。"""
    now = time.time() if now is None else now
    if not runs_root.exists():
        return []
    active = []
    for entry in sorted(runs_root.iterdir()):
        if "d11_p0" not in entry.name or not entry.is_dir():
            continue
        age = now - latest_mtime(entry)
        if age < quiet_s:
            active.append({"dir": str(entry), "newest_update_age_s": round(age, 1)})
    return active


def w0_checks(campaign: str = "a1") -> dict[str, dict]:
    cfg = CAMPAIGNS[campaign]
    lines = COORD_LOG.read_text(encoding="utf-8").splitlines()
    release = [line for line in lines if cfg["release_re"].match(line)]
    probes = procs_matching(lambda argv, cwd: any(Path(a).name == "stall_probe.py" for a in argv))
    d11p0_dirs = active_d11p0_dirs()
    d09 = procs_matching(lambda argv, cwd: cwd.startswith(D09_DIR)
                         and any(Path(a).name in ("runner.py", "b_runner.py") for a in argv))
    env_keys = sorted(k for k in os.environ if k.startswith(("FT_", "FREETOKEN_")))
    active = json.loads(PRODUCTION_ACTIVE.read_text()) if PRODUCTION_ACTIVE.exists() else {}
    health = production_health()
    lock = json.loads(GPU_LOCK.read_text()) if GPU_LOCK.exists() else {}
    approval = active.get("approval_id")
    checks: dict[str, dict] = {
        "main_session_release_line": {"pass": bool(release), "evidence": release[-1] if release else None},
    }
    if campaign == "a2":
        ready = [line for line in lines if A2_READY_LINE_RE.match(line)]
        checks["op_hak_a2_ready_line"] = {"pass": bool(ready), "evidence": ready[-1] if ready else None}
    checks.update({
        "d11p0_not_running": {"pass": not probes and not d11p0_dirs, "stall_probe_pids": probes,
                              "active_d11p0_dirs": d11p0_dirs},
        "no_stall_probe": {"pass": not probes, "pids": probes},
        "no_d09_window_process": {"pass": not d09, "pids": d09},
        "no_task_a_stop_file_server": {"pass": not TASK_A_STOP.exists()},
        "no_ft_env": {"pass": not env_keys, "keys": env_keys},
        "production_serving": {"pass": approval == cfg["approval"]
                               and health.get("status") == "ok" and health.get("maintenance") == "serving",
                               "approval_id": approval, "expected_approval": cfg["approval"], "health": health},
        "gpu_lock_is_production": {"pass": lock.get("owner") == f"production:release:{approval}",
                                   "owner": lock.get("owner")},
    })
    return checks


def cmd_w0_check(campaign: str) -> int:
    cfg = CAMPAIGNS[campaign]
    checks = w0_checks(campaign)
    all_pass = all(item["pass"] for item in checks.values())
    active = json.loads(PRODUCTION_ACTIVE.read_text()) if PRODUCTION_ACTIVE.exists() else {}
    result = {"campaign": campaign, "checked_at": server_now(), "all_pass": all_pass, "checks": checks,
              "baseline_argv": active.get("argv"), "approval_id": active.get("approval_id")}
    cfg["w0_result"].write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all_pass else 3


def post_stop_preconditions(campaign: str = "a1") -> dict[str, dict]:
    """W3 停服之后、W4 开窗之前。"""
    cfg = CAMPAIGNS[campaign]
    compute = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                                      text=True).strip()
    port_free = True
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((SERVE_HOST, SERVE_PORT))
        except OSError:
            port_free = False
    serves = procs_matching(lambda argv, cwd: "serve" in argv and any(a.endswith("/ft") for a in argv))
    return {
        "production_stopped": {"pass": cfg["stopped"].exists() and not PRODUCTION_ACTIVE.exists(),
                               "stopped_json": str(cfg["stopped"])},
        "gpu_lock_absent": {"pass": not GPU_LOCK.exists()},
        "gpu_compute_empty": {"pass": compute == ""},
        "port_8123_free": {"pass": port_free},
        "no_ft_serve": {"pass": not serves, "pids": serves},
    }


def analyze_for(window_dir: Path, prereg: dict, inputs: dict, trajectories: tuple[str, ...]) -> dict:
    """A2（只跑 T2）用 analyze_task_a2；A1 用 analyze_task_a。"""
    if trajectories == ("T2",):
        from analyze_task_a2 import analyze_run_t2  # noqa: WPS433 - 同目录导入
        return analyze_run_t2(window_dir, prereg, inputs)
    from analyze_task_a import analyze_run  # noqa: WPS433
    return analyze_run(window_dir, prereg, inputs)


def cmd_window(run_dir: Path, campaign: str) -> int:
    cfg = CAMPAIGNS[campaign]
    if not cfg["w0_result"].exists():
        raise RunnerError(f"缺少 {cfg['w0_result'].name}，先运行 w0-check --campaign {campaign}")
    w0 = json.loads(cfg["w0_result"].read_text())
    age = time.time() - datetime.fromisoformat(w0["checked_at"]).timestamp()
    if not w0["all_pass"] or age > W0_MAX_AGE_S:
        raise RunnerError("W0 结果未通过或已过期，重新运行 w0-check")
    checks = post_stop_preconditions(campaign)
    if not all(item["pass"] for item in checks.values()):
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        raise RunnerError("W3 之后的前置检查不通过，不开窗")
    prereg, inputs = load_prereg(), load_inputs()
    launcher = RealLauncher(w0["baseline_argv"])
    trajectories = cfg["trajectories"]
    summary = run_window(launcher, SERVICES, run_dir / "window",
                         lambda arm: build_plan(inputs, prereg, arm, trajectories),
                         limit_s=cfg["limit_s"], reserve_s=cfg["reserve_s"])
    write_new(run_dir / "analysis.json", analyze_for(run_dir / "window", prereg, inputs, trajectories))
    print(json.dumps({"terminal": summary["terminal"]}, ensure_ascii=False))
    return 0 if summary["terminal"] == "complete" else 4


def cmd_rehearse(run_dir: Path, port: int, scale: float, inject: dict,
                 trajectories: tuple[str, ...] = ("seed_real", "T2")) -> int:
    prereg, inputs = load_prereg(), load_inputs()
    launcher = StubLauncher(port, scale, inject)
    summary = run_window(launcher, SERVICES, run_dir / "window",
                         lambda arm: build_plan(inputs, prereg, arm, trajectories),
                         limit_s=CAMPAIGNS["a2"]["limit_s"] if trajectories == ("T2",) else WINDOW_LIMIT_S,
                         reserve_s=CAMPAIGNS["a2"]["reserve_s"] if trajectories == ("T2",) else SERVICE_RESERVE_S)
    analysis = analyze_for(run_dir / "window", prereg, inputs, trajectories)
    write_new(run_dir / "analysis.json", analysis)
    print(json.dumps({"terminal": summary["terminal"],
                      "services": [(s["service"], s["status"], s.get("done")) for s in summary["services"]]},
                     ensure_ascii=False))
    return 0 if summary["terminal"] == "complete" else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="op-hak 任务 A 工装（只测量，不判定）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rehearse = sub.add_parser("rehearse", help="CPU 演练（桩服务）")
    rehearse.add_argument("--run-dir", type=Path, required=True)
    rehearse.add_argument("--port", type=int, default=18300)
    rehearse.add_argument("--scale", type=float, default=1.0)
    rehearse.add_argument("--inject-json", default="{}")
    rehearse.add_argument("--trajectories", default="seed_real,T2", help="如 T2（A2）或 seed_real,T2（A1）")
    w0 = sub.add_parser("w0-check", help="只读检查 W0")
    w0.add_argument("--campaign", choices=sorted(CAMPAIGNS), required=True)
    window = sub.add_parser("window", help="真实 W4 窗口（P2）")
    window.add_argument("--run-dir", type=Path, required=True)
    window.add_argument("--campaign", choices=sorted(CAMPAIGNS), required=True)
    args = parser.parse_args(argv)
    if args.cmd == "rehearse":
        trajectories = tuple(t for t in args.trajectories.split(",") if t)
        return cmd_rehearse(args.run_dir, args.port, args.scale, json.loads(args.inject_json), trajectories)
    if args.cmd == "w0-check":
        return cmd_w0_check(args.campaign)
    return cmd_window(args.run_dir, args.campaign)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"RUNNER STOP: {exc}", file=sys.stderr)
        raise SystemExit(2)
