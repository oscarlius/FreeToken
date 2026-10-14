#!/usr/bin/env python3
"""op-hak 任务 B 工装：任务 A2 的 task_a_runner.py（112917c56034）改三处（任务 B §3）：
  1. 构建门：每个服务用哪个构建（release-e2 / 候选工作树）由服务定义决定；启动前用同一解释器与 PYTHONPATH
     导入 freetoken.scheduler.prefill，实际路径不在该构建下则拒绝启动（BuildGateError，窗口停止）。
  2. 参数门：B 臂多一个 --prefill-anchor-cut-min-tokens 32768；就绪后读 serve.log 的 Parsed arguments，
     值与臂不符则停止该窗口（param_gate_refused）。
  3. 单服务 OOM 处理：OOM 或 worker 退出只关掉该服务（只关我方进程），继续下一个服务；
     同一窗口第二次此类退出：停窗（second_death_stop），然后走恢复流程。服务与轮次写入窗口记录。
其余逻辑与 A2 相同（请求计划、SSE 解析、监视、清场、argv 门、W0）。

命令（在 WORK 目录下运行，服务器上用 venv 的 python）：
  rehearse --run-dir DIR [--port P] [--scale S] [--inject-json JSON]   （CPU 演练，桩服务）
  w0-check --campaign b
  window --run-dir DIR --campaign b                                                  （P2，GPU 窗口）

本文件不写判读结论。判读由 analyze_task_b.py 按预登记 PREREG_TASK_B_v2 机械计算。
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
W0_RESULT_B = WORK / "W0_CHECK_B.json"
PREREG_PATH = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_B_v2.json")
PREREG_SHA256 = "8df5ee4901795d287bed22cfaadbaef3515c89f530c4f9df26a5798489f9152d"
PRODUCTION_ACTIVE = Path("/data2/FreeToken/run/production.active.json")
B_STOPPED = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-12/stopped.json")  # 任务 B 窗口开始时的生产（-12）停服回执
PRODUCTION_ENDPOINT = "http://172.16.108.9:8095"
COORD_LOG = Path("/data2/FreeToken/plan/COORDINATION_LOG.md")
TASK_A_STOP = Path("/data2/FreeToken/plan/OPHAK_TASK_A_STOP.md")
GPU_LOCK = Path("/data2/_shared/gpu.lock")
D09_DIR = "/data2/FreeToken/development/gemini_d09_enable_20261011"
OH_WINDOW_PATH = Path("/data2/FreeToken/development/gemini_oom_hybrid_20261011/oh_window.py")
RELEASE_PYTHONPATH = "/data2/FreeToken/wt/release-e2/python"
CANDIDATE_PYTHONPATH = "/data2/FreeToken/wt/m1-cutmin-20261011/python"  # 候选：分支 m1/cut-min-tokens，提交 9db0ee77（只在本地）
BUILD_ROOTS = {"release": RELEASE_PYTHONPATH, "candidate": CANDIDATE_PYTHONPATH}
FT_PYTHON = "/data2/FreeToken/venv/bin/python3"  # 与 ft 入口的解释器相同（shebang）
MIN_TOKENS_THRESH = 32768  # B 臂阈值（预登记 policy）
MODEL = "Qwen3.8-Flash-Next-NVFP4"
SERVE_HOST = "127.0.0.1"
SERVE_PORT = 8123
SERVICES: tuple[tuple[str, str, str], ...] = (  # (名称, 臂, 构建)；顺序固定（§4.1）
    ("R0", "on", "release"), ("C_A1", "on", "candidate"), ("C_B1", "thresh", "candidate"),
    ("C_B2", "thresh", "candidate"), ("C_A2", "on", "candidate"))
WINDOW_LIMIT_S = 3600.0          # W4：总时限 60 分钟
SERVICE_RESERVE_S = 480.0        # 每个服务约 7–8 分钟；剩余不足则不开新服务（§5 超时路由）
READY_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 600.0
BETWEEN_REQUESTS_S = 1.0         # §2.2：前一条收到 usage 后，至少间隔 1 秒
SETTLE_LOG_S = 0.3               # 请求结束后等 serve.log 刷盘
W0_MAX_AGE_S = 2700.0
PREFILL_LINE_RE = re.compile(r"Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)")
B_RELEASE_LINE_RE = re.compile(r"^- \S+ 主会话.*任务 B 放行")
OOM_MARKERS = ("out of memory", "worker_restarting_after_oom")

# ---- 任务 B（plan/OPHAK_TASK_B_CUT_POLICY_20261011.md §3–§5）
B_READY_LINE_RE = re.compile(r"^- \S+ op-hak：任务 B P1 就绪")
S_REVIEW_LINE_RE = re.compile(r"^- \S+ 主会话.*任务 S 复核")  # W0：任务 S 已由主会话复核
S_END_LINE_RE = re.compile(r"^- \S+ op-hak：任务 S 窗口结束")  # W0：任务 S 的结束记录存在
WATCH_POLL_S = 5.0          # §3.2：请求进行中每 5 秒检查一次 serve.log（判定）与 /health（只记录，不作判据）
OOM_TEXT_RE = re.compile(r"out of memory", re.IGNORECASE)  # 原文：RuntimeError: Triton Error [CUDA]: out of memory
WORKER_MARKER_RE = re.compile(r"backend worker \S+ exited|backend worker is gone", re.IGNORECASE)
# 原文：Backend supervisor: backend worker freetoken-TP0-scheduler exited / Backend worker is gone and cannot be restarted
# 任务 B 战役参数（§4.2）：总时限 60 分钟，保留 8 分钟。审批号为窗口开始时生产的审批号（W0 核对）。
CAMPAIGNS: dict[str, dict[str, Any]] = {
    "b": {"trajectories": ("seed_real", "T2"), "limit_s": WINDOW_LIMIT_S, "reserve_s": SERVICE_RESERVE_S,
          "approval": "RESTORE481-MORNING-20261011-12", "release_re": B_RELEASE_LINE_RE,
          "stopped": B_STOPPED, "w0_result": W0_RESULT_B},
}
D11P0_RUNS_ROOT = Path("/data2/FreeToken/runs")
D11P0_QUIET_S = 600.0  # 补充 1 第 3 节：runs 下名称含 d11_p0 的目录，最近 10 分钟内有文件更新即视为 D11-P0 仍在运行


class RunnerError(RuntimeError):
    """指令没有覆盖的情况，或前置条件不满足。"""


class LaunchError(RuntimeError):
    """服务没有起来，或 argv 门不通过。"""


class BuildGateError(LaunchError):
    """构建门不通过：实际导入的 freetoken 不在该服务应有的构建之下（任务 B §3 第 1 条）。"""


class ParamGateError(RuntimeError):
    """参数门不通过：serve.log 的 Parsed arguments 与该构建与臂应有的值不符（任务 B §3 第 2 条）。"""


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


def prereg_round(prereg: dict, trajectory: str, k: int) -> dict:
    """B 预登记：trajectories[轨迹] 为列表，按 round 查找唯一的一项。"""
    matches = [spec for spec in prereg["trajectories"][trajectory] if spec["round"] == k]
    if len(matches) != 1:
        raise RunnerError(f"预登记中找不到唯一的轮次：{trajectory}/{k}")
    return matches[0]


def build_plan(inputs: dict, prereg: dict, arm: str,
               trajectories: tuple[str, ...] = ("seed_real", "T2")) -> list[dict]:
    """warmup，然后所选轨迹的轮次：seed_real 第 0–7 轮，再 T2 第 0–11 轮（与任务 A 相同的 20 个 payload 与顺序）。
    arm：on 取 on_segments（N = 0）；thresh 取 thresh_segments（N = 32768）。"""
    if arm not in ("on", "thresh"):
        raise RunnerError(f"未知臂：{arm}")
    if not trajectories or any(t not in ("seed_real", "T2") for t in trajectories):
        raise RunnerError(f"未知轨迹：{trajectories}")
    items = [plan_item("warm/00", inputs["warmup"], None)]
    for row in inputs["rounds"]:
        if row["trajectory"] not in trajectories:
            continue
        spec = prereg_round(prereg, row["trajectory"], row["round"])
        if spec["prompt_tokens"] != row["prompt_tokens"]:
            raise RunnerError(f'预登记与输入的 prompt_tokens 不符：{row["trajectory"]}/{row["round"]}')
        expect = {"prompt_tokens": spec["prompt_tokens"], "cached": spec["cached"], "class": spec["class"],
                  "segments": spec["on_segments"] if arm == "on" else spec["thresh_segments"]}
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
                # OOM 与 worker 退出：中止本服务，不重试，并记下死亡的轮次；第二次死亡由 run_window 停窗
                summary.update(status=record["status"], died_at_key=item["key"],
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

def extra_argv(arm: str) -> list[str]:
    """臂对应的额外参数：on（N = 0，与生产相同）不加任何参数；thresh（N = 32768）只加阈值参数。"""
    if arm == "on":
        return []
    if arm == "thresh":
        return ["--prefill-anchor-cut-min-tokens", str(MIN_TOKENS_THRESH)]
    raise LaunchError(f"未知臂：{arm}")


def build_argv(baseline: list[str], arm: str) -> tuple[list[str], list[dict]]:
    """生产 argv 只改 host 与 port，再追加臂的额外参数（extra_argv）。其它差异一律拒绝。"""
    if baseline[:3] != ["taskset", "-c", "1,3-47"]:
        raise LaunchError("生产 argv 的绑核前缀与预期不同")
    expected = list(baseline)
    for flag, value in (("--host", SERVE_HOST), ("--port", str(SERVE_PORT))):
        if expected.count(flag) != 1:
            raise LaunchError(f"生产 argv 中 {flag} 出现次数不是 1")
        expected[expected.index(flag) + 1] = value
    extra = extra_argv(arm)
    expected += extra
    diff = [{"index": i, "baseline": a, "actual": b} for i, (a, b) in enumerate(zip(baseline, expected)) if a != b]
    diff += [{"index": len(baseline) + j, "baseline": None, "actual": t} for j, t in enumerate(extra)]
    return expected, diff


def verify_argv(baseline: list[str], actual: list[str], arm: str) -> list[dict]:
    expected, diff = build_argv(baseline, arm)
    if actual != expected:
        raise LaunchError(f"argv 与允许的差异不符（臂 {arm}）")
    return diff


def build_root(build: str) -> str:
    """构建名到 PYTHONPATH 根目录；未知构建拒绝。"""
    if build not in BUILD_ROOTS:
        raise LaunchError(f"未知构建：{build}")
    return BUILD_ROOTS[build]


def clean_env(base: dict[str, str] | None = None, build: str = "release") -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in [k for k in env if k.startswith(("FT_", "FREETOKEN_"))]:
        del env[key]
    env.update({"PYTHONPATH": build_root(build), "MASTER_PORT": "8096",
                "CUDA_VISIBLE_DEVICES": "0", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


# ---------------------------------------------------------------- 构建门与参数门（任务 B §3）

PROBE_CODE = "import freetoken.scheduler.prefill as m; print(m.__file__)"
PARSED_HEADER = "Parsed arguments:"  # args.py：logger.info(f"Parsed arguments:\n{result}")，result 为 ServerArgs 的单行 repr
MIN_TOKENS_RE = re.compile(r"prefill_anchor_cut_min_tokens=(\d+)")


def check_build(build: str, env: dict[str, str], out_dir: Path, *, python: str = FT_PYTHON) -> dict:
    """构建门：用同一解释器与同一 PYTHONPATH 导入 freetoken.scheduler.prefill，实际路径必须在该构建的根目录之下。
    结果写入 out_dir/build_gate.json（通过与否都写）；不通过抛 BuildGateError，窗口停止。"""
    root = build_root(build)
    try:
        probe = subprocess.run([python, "-B", "-c", PROBE_CODE], env=env, capture_output=True, text=True,
                               timeout=300)
        lines = probe.stdout.strip().splitlines()
        actual, returncode = (lines[-1] if lines else ""), probe.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        actual, returncode = f"probe_failed:{exc!r}", None
    ok = returncode == 0 and actual.startswith(root + "/")
    record = {"build": build, "python": python, "pythonpath": env.get("PYTHONPATH"), "expected_root": root,
              "imported": actual, "returncode": returncode, "ok": ok}
    write_new(out_dir / "build_gate.json", record)
    if not ok:
        raise BuildGateError(f"构建门不通过（{build}）：导入 {actual!r}，期望在 {root}/ 之下，返回码 {returncode}")
    return record


def expected_min_tokens(build: str, arm: str) -> int | None:
    """该构建与臂应有的 prefill_anchor_cut_min_tokens。release-e2 没有此参数（None）；候选 on 为 0，thresh 为 32768。"""
    build_root(build)
    if arm not in ("on", "thresh"):
        raise LaunchError(f"未知臂：{arm}")
    if build == "release":
        if arm != "on":
            raise LaunchError("release-e2 没有该参数，只能跑 on 臂")
        return None
    return 0 if arm == "on" else MIN_TOKENS_THRESH


def parsed_min_tokens(serve_log: Path) -> int | None:
    """serve.log 中 Parsed arguments 紧随的那一行里的 prefill_anchor_cut_min_tokens；字段不存在返回 None。
    只看该行，避免别处的同名文字干扰。没有 Parsed arguments 记录则抛 ParamGateError。"""
    text = serve_log.read_text(encoding="utf-8", errors="replace")
    at = text.find(PARSED_HEADER)
    if at < 0:
        raise ParamGateError("serve.log 中没有 Parsed arguments 记录")
    after = text[at + len(PARSED_HEADER):].lstrip("\n").split("\n", 1)[0]
    match = MIN_TOKENS_RE.search(after)
    return int(match.group(1)) if match else None


def param_gate(serve_log: Path, build: str, arm: str, out_dir: Path) -> int | None:
    """参数门：服务就绪后核对实际解析的参数，与该构建与臂应有的值一致才放行（任务 B §3 第 2 条）。
    结果写入 out_dir/param_gate.json（通过与否都写）。"""
    expected = expected_min_tokens(build, arm)
    try:
        actual = parsed_min_tokens(serve_log)
    except ParamGateError as exc:
        write_new(out_dir / "param_gate.json", {"build": build, "arm": arm, "expected": expected,
                                                "actual": None, "error": str(exc), "ok": False})
        raise
    ok = actual == expected
    write_new(out_dir / "param_gate.json", {"build": build, "arm": arm, "expected": expected,
                                            "actual": actual, "ok": ok})
    if not ok:
        raise ParamGateError(f"参数门不通过（构建 {build}，臂 {arm}）：期望 {expected}，serve.log 实际 {actual}")
    return actual


def startup_status(serve_log: Path) -> str:
    """服务没有就绪：serve.log 已有 OOM 或 worker 退出标记则按死亡计（计入第二次停窗），否则为普通启动失败。"""
    text = serve_log.read_text(encoding="utf-8", errors="replace")
    if OOM_TEXT_RE.search(text):
        return "oom"
    if WORKER_MARKER_RE.search(text):
        return "worker_exit"
    return "launch_failed"


def wait_ready(endpoint: str, *, timeout_s: float, sleep: Callable[[float], None] = time.sleep,
               clock: Callable[[], float] = time.monotonic, proc: subprocess.Popen | None = None) -> bool:
    """等待 /health 为 serving。进程先退出（没到 ready 就退出）则立即返回 False，不再等满超时。"""
    t0 = clock()
    with httpx.Client(trust_env=False, timeout=2.0) as client:
        while clock() - t0 < timeout_s:
            if proc is not None and proc.poll() is not None:
                return False
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

    def start(self, name: str, arm: str, out_dir: Path, build: str = "release") -> Handle:
        out_dir.mkdir(parents=True, exist_ok=False)
        options = dict(self.inject.get(name, {}))
        env = clean_env(build=build)
        env.update({"CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": options.pop("pythonpath", env["PYTHONPATH"])})
        check_build(build, env, out_dir)  # 构建门照常执行；不通过则抛 BuildGateError，不启动桩服务
        parsed = options.pop("parsed-min-tokens", None)
        if parsed is None:
            expected = expected_min_tokens(build, arm)
            parsed = "absent" if expected is None else str(expected)
        serve_log = out_dir / "serve.log"
        serve_log.touch()
        args = [sys.executable, "-B", str(WORK / "stub_b_server.py"), "--port", str(self.port),
                "--arm", arm, "--serve-log", str(serve_log), "--stats-out", str(out_dir / "stub_stats.jsonl"),
                "--inputs", str(INPUTS_JSON), "--prereg", str(PREREG_PATH), "--scale", str(self.scale),
                "--parsed-min-tokens", parsed]
        for flag, value in options.items():
            args += [f"--{flag}", value]
        with (out_dir / "stub_stdout.log").open("wb") as stdout:
            proc = subprocess.Popen(args, cwd=str(out_dir), stdout=stdout, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        endpoint = f"http://{SERVE_HOST}:{self.port}"
        ready = wait_ready(endpoint, timeout_s=READY_TIMEOUT_S, proc=proc)
        return Handle(name, arm, endpoint, serve_log, out_dir, proc=proc, ready=ready)

    def stop(self, handle: Handle) -> bool:
        if handle.proc.poll() is not None:
            return True  # 没到 ready 就退出的进程已经结束，无需再关
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

    def start(self, name: str, arm: str, out_dir: Path, build: str = "release") -> Handle:
        argv, diff = build_argv(self.baseline, arm)
        extra = extra_argv(arm)
        if self.oh.compute_expected_argv(self.baseline, {"type": "offload", "extra_argv": extra},
                                         host=SERVE_HOST, port=SERVE_PORT) != argv:
            raise LaunchError("oh_window 的 argv 计算与本工装不一致，停止")
        out_dir.mkdir(parents=True, exist_ok=False)
        env = clean_env(build=build)
        check_build(build, env, out_dir)  # 构建门：在占 GPU 锁与启动之前
        write_new(out_dir / "argv_diff.json", {"arm": arm, "build": build, "argv": argv, "diff": diff})
        try:
            self.oh.idle(self.d07, [(SERVE_HOST, SERVE_PORT)])
        except Exception as exc:  # noqa: BLE001 - 任何非空闲状态都是启动前失败
            raise LaunchError(f"启动前检查不通过：{exc!r}") from exc
        owner = self.d07.take_d07_gpu_lock(f"OPHAK-TASKA-20261011-{name}", 0)
        serve_log = out_dir / "serve.log"
        log_handle = None
        try:
            log_handle = serve_log.open("xb")
            proc = subprocess.Popen(argv, cwd=str(out_dir), env=env, stdout=log_handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except Exception as exc:  # noqa: BLE001 - 任何启动前失败都先释放 GPU 锁
            if log_handle is not None:
                log_handle.close()
            self.d07.release_d07_gpu_lock(owner)
            raise LaunchError(f"spawn failed: {exc!r}") from exc
        try:
            birth = self.oh.capture_birth(proc, self.d07)
        except Exception as exc:  # noqa: BLE001 - 取不到身份：只关本次子进程、释放锁，计为启动失败
            self._abort_child(proc, log_handle, owner)
            raise LaunchError(f"capture_birth failed: {exc!r}") from exc
        endpoint = f"http://{SERVE_HOST}:{SERVE_PORT}"
        ready = wait_ready(endpoint, timeout_s=READY_TIMEOUT_S, proc=proc)
        return Handle(name, arm, endpoint, serve_log, out_dir, proc=proc, ready=ready,
                      birth=birth, owner=owner, log_handle=log_handle)

    def _abort_child(self, proc: subprocess.Popen, log_handle: Any, owner: Any) -> None:
        """启动失败的清场：只关掉本次启动的子进程组（我方进程），关日志，释放 GPU 锁。"""
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        log_handle.close()
        self.d07.release_d07_gpu_lock(owner)

    def stop(self, handle: Handle) -> bool:
        ok = self.oh.cleanup(handle.proc, handle.birth, self.d07, handle.out_dir,
                             [(SERVE_HOST, SERVE_PORT)])
        handle.log_handle.close()
        if ok:
            self.d07.release_d07_gpu_lock(handle.owner)
        return ok


# ---------------------------------------------------------------- 窗口编排

DEATH_STATUSES = ("oom", "worker_exit", "launch_failed")  # 服务死亡：三者合并计数（freetoken-06 裁定）


def count_death(summary: dict[str, Any], name: str, status: str, key: str | None) -> bool:
    """记一次服务死亡。同一窗口累计第二次：置 second_death_stop 并返回 True（调用方停窗，按 W5 恢复 481）。"""
    summary["deaths"].append({"service": name, "status": status, "key": key})
    if len(summary["deaths"]) >= 2:
        summary["terminal"] = "second_death_stop"
        return True
    return False


def safe_stop(launcher: Any, handle: Handle) -> tuple[bool, str | None]:
    """清场。清场本身抛异常只算清场失败（cleanup_blocked），不让异常穿过窗口编排。"""
    try:
        return bool(launcher.stop(handle)), None
    except Exception as exc:  # noqa: BLE001
        return False, repr(exc)


def run_window(launcher: Any, services: tuple[tuple[str, ...], ...], out_dir: Path,
               plan_for_arm: Callable[[str], list[dict]], *, transport=None,
               sleep: Callable[[float], None] = time.sleep, between_s: float = BETWEEN_REQUESTS_S,
               clock: Callable[[], float] = time.monotonic, limit_s: float = WINDOW_LIMIT_S,
               reserve_s: float = SERVICE_RESERVE_S) -> dict:
    """按固定顺序跑服务，服务为 (名称, 臂[, 构建])，缺省构建为 release。
    服务死亡（OOM、worker 退出、没到 ready 的启动失败）合并计数：第一次关掉该服务、继续下一个；
    同一窗口累计第二次：停窗（second_death_stop），按 W5 恢复 481。构建门、参数门、请求错误、清理失败、工装异常：停窗。"""
    out_dir.mkdir(parents=True, exist_ok=False)
    started = clock()
    summary: dict[str, Any] = {"schema": "ophak_task_b_window/v1", "started_at": server_now(),
                               "services": [], "deaths": [], "terminal": None}
    for service in services:
        name, arm, build = (tuple(service) + ("release",))[:3]
        if limit_s - (clock() - started) < reserve_s:
            summary["terminal"] = "time_limit"
            break
        try:
            handle = launcher.start(name, arm, out_dir / name, build)
        except BuildGateError as exc:
            summary["services"].append({"service": name, "arm": arm, "build": build,
                                        "status": "build_gate_refused", "stop_reason": str(exc)})
            summary["terminal"] = "build_gate_refused"
            break
        except Exception as exc:  # noqa: BLE001 - LaunchError 与其它启动前失败一样计为一次死亡
            summary["services"].append({"service": name, "arm": arm, "build": build,
                                        "status": "launch_failed", "stop_reason": repr(exc)})
            if count_death(summary, name, "launch_failed", None):
                break
            continue
        result: dict[str, Any]
        try:
            if handle.ready:
                # §2.3：服务就绪时也采一次显存（只记录）
                write_new(handle.out_dir / "memory_ready.json",
                          {"memory_used_mib": MEMORY_SAMPLER(), "sampled_at": server_now()})
                param_gate(handle.serve_log, build, arm, handle.out_dir)  # 参数门（§3 第 2 条）：不符则抛 ParamGateError
                result = run_service(handle.endpoint, name, arm, handle.serve_log, handle.out_dir,
                                     plan_for_arm(arm), transport=transport, sleep=sleep, between_s=between_s)
            else:
                result = {"service": name, "arm": arm, "status": startup_status(handle.serve_log),
                          "stop_reason": "没到 ready（进程退出或超时）"}
        except ParamGateError as exc:
            result = {"service": name, "arm": arm, "status": "param_gate_refused", "stop_reason": str(exc)}
        except Exception as exc:  # noqa: BLE001 - 工装异常：记录后清场并停止窗口
            result = {"service": name, "arm": arm, "status": "runner_exception", "stop_reason": repr(exc)}
        finally:
            cleaned, cleanup_error = safe_stop(launcher, handle)
        result.update(build=build, cleanup_ok=cleaned, cleanup_error=cleanup_error)
        summary["services"].append(result)
        if not cleaned:
            (out_dir / "CLEANUP_BLOCKED.md").write_text(
                f"清理失败：{name}（{cleanup_error or '清场返回失败'}）。GPU 锁未释放，窗口中止，需要主会话处理。\n",
                encoding="utf-8")
            summary["terminal"] = "cleanup_blocked"
            break
        if result["status"] in DEATH_STATUSES:
            if count_death(summary, name, result["status"], result.get("died_at_key")):
                break
            continue
        if result["status"] in ("request_error", "runner_exception", "param_gate_refused"):
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


def w0_checks(campaign: str = "b") -> dict[str, dict]:
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
    if campaign == "b":
        for label, pattern in (("op_hak_b_ready_line", B_READY_LINE_RE), ("task_s_reviewed_line", S_REVIEW_LINE_RE),
                               ("task_s_window_end_line", S_END_LINE_RE)):
            found = [line for line in lines if pattern.match(line)]
            checks[label] = {"pass": bool(found), "evidence": found[-1] if found else None}
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


def post_stop_preconditions(campaign: str = "b") -> dict[str, dict]:
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


def analyze_for(window_dir: Path, prereg: dict, inputs: dict) -> dict:
    """任务 B：analyze_task_b 按预登记 v2 机械计算（T16-lite、G1–G5、漂移）；工装不写判读结论。"""
    from analyze_task_b import analyze_run_b  # noqa: WPS433 - 同目录导入
    return analyze_run_b(window_dir, prereg, inputs)


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
    write_new(run_dir / "analysis.json", analyze_for(run_dir / "window", prereg, inputs))
    print(json.dumps({"terminal": summary["terminal"]}, ensure_ascii=False))
    return 0 if summary["terminal"] == "complete" else 4


def cmd_rehearse(run_dir: Path, port: int, scale: float, inject: dict,
                 trajectories: tuple[str, ...] = ("seed_real", "T2")) -> int:
    prereg, inputs = load_prereg(), load_inputs()
    launcher = StubLauncher(port, scale, inject)
    summary = run_window(launcher, SERVICES, run_dir / "window",
                         lambda arm: build_plan(inputs, prereg, arm, trajectories),
                         limit_s=CAMPAIGNS["b"]["limit_s"], reserve_s=CAMPAIGNS["b"]["reserve_s"])
    analysis = analyze_for(run_dir / "window", prereg, inputs)
    write_new(run_dir / "analysis.json", analysis)
    print(json.dumps({"terminal": summary["terminal"],
                      "services": [(s["service"], s["status"], s.get("done")) for s in summary["services"]]},
                     ensure_ascii=False))
    return 0 if summary["terminal"] == "complete" else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="op-hak 任务 B 工装（只测量，不判定）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rehearse = sub.add_parser("rehearse", help="CPU 演练（桩服务）")
    rehearse.add_argument("--run-dir", type=Path, required=True)
    rehearse.add_argument("--port", type=int, default=18300)
    rehearse.add_argument("--scale", type=float, default=1.0)
    rehearse.add_argument("--inject-json", default="{}")
    rehearse.add_argument("--trajectories", default="seed_real,T2", help="默认 seed_real,T2（任务 B 全量）")
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
