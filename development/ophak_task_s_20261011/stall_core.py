#!/usr/bin/env python3
"""任务 S 的纯计算（不做 I/O）：停顿 G、零输出、结构两级、混入、单事件与总判。

判据取自 PREREG_TASK_S_v2.json 的 gates，与 OPHAK_TASK_S_STALL_20261011.md §3–§5、§7 一致。
时间单位为秒（单调时钟）。缩放演练（scale < 1）时，时间常数与预登记区间按同一系数缩放；
正式结论只采用 scale = 1 的运行。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Sequence

PREFILL_LINE_RE = re.compile(r"Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)")
OOM_TEXT_RE = re.compile(r"out of memory", re.IGNORECASE)
WORKER_MARKER_RE = re.compile(r"backend worker \S+ exited|backend worker is gone", re.IGNORECASE)
MODEL = "Qwen3.8-Flash-Next-NVFP4"
A_PROMPT = "从 1 开始，每行写一个整数，一直写下去。"
A_MAX_TOKENS = 16384
L64_MAX_TOKENS_OLD = 2048
L64_MAX_TOKENS_NEW = 32
L64_SHA256 = "261d50af3092dfabd20514e6ad06393be4e5265a1e2b9d95c158746946356618"
A_START_DELTAS = 50
A_AFTER_B_DELTAS = 30
MIN_N_FOR_JUDGMENT = 9
PREREG_ZERO_LEAD_S = 0.4
PREREG_ZERO_TRAIL_S = 0.2
PREREG_MARGIN_S = 2.0
PREREG_A_RESTART_S = 300.0
PREREG_TOTAL_LIMIT_S = 900.0
PREREG_EMERGENCY_S = 300.0
PREREG_STATS_S = 0.5
PREREG_HEALTH_S = 5.0
PREREG_PRECHECK_S = 60.0
PREREG_PRECHECK_STEP_S = 5.0
SETTLE_S = 0.5
ACTIVE_WAIT_S = 60.0
A_DELTA_WAIT_S = 120.0


class Timing:
    """所有时间常数（秒）。scale 为缩放系数：演练时 < 1，正式运行为 1。"""

    def __init__(self, scale: float = 1.0, a_restart_s: float | None = None) -> None:
        if not 0 < scale <= 1:
            raise ValueError("scale 必须在 (0, 1] 内")
        self.scale = scale
        self.margin_s = PREREG_MARGIN_S * scale
        self.zero_lead_s = PREREG_ZERO_LEAD_S * scale
        self.zero_trail_s = PREREG_ZERO_TRAIL_S * scale
        # 仅演练用：缩放演练中 A 的运行时长达不到 300 秒，用覆盖值让重启机制可被触发。正式运行不传。
        self.a_restart_s = PREREG_A_RESTART_S * scale if a_restart_s is None else float(a_restart_s)
        self.total_limit_s = PREREG_TOTAL_LIMIT_S * scale
        self.emergency_s = PREREG_EMERGENCY_S * scale
        self.stats_s = PREREG_STATS_S * scale
        self.health_s = PREREG_HEALTH_S * scale
        self.precheck_s = PREREG_PRECHECK_S * scale
        self.precheck_step_s = PREREG_PRECHECK_STEP_S * scale
        self.settle_s = SETTLE_S * scale
        self.active_wait_s = ACTIVE_WAIT_S * scale
        self.a_delta_wait_s = A_DELTA_WAIT_S * scale

    def band(self, band: Sequence[float]) -> tuple[float, float]:
        return (band[0] * self.scale, band[1] * self.scale)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def messages_sha256(messages: list[dict]) -> str:
    """与任务 A 的 freeze_inputs / 桩服务相同的口径：messages 的规范 JSON 的 SHA256。"""
    return sha256_hex(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def build_a_body() -> bytes:
    """指令 §3.1 的会话 A 载荷，逐字段固定，不带 tools。"""
    payload = {"model": MODEL, "messages": [{"role": "user", "content": A_PROMPT}], "temperature": 0,
               "max_tokens": A_MAX_TOKENS, "ignore_eos": True, "stream": True,
               "stream_options": {"include_usage": True}}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def build_l64_body(raw: bytes) -> bytes:
    """指令 §3.2：先校验原文件 SHA256，再只把 max_tokens 从 2048 改为 32，其余字段不改。"""
    if sha256_hex(raw) != L64_SHA256:
        raise ValueError("L64.json 原文件 SHA256 不符")
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("max_tokens") != L64_MAX_TOKENS_OLD:
        raise ValueError(f"L64 原 max_tokens 应为 {L64_MAX_TOKENS_OLD}，实为 {doc.get('max_tokens')}")
    changed = dict(doc)
    changed["max_tokens"] = L64_MAX_TOKENS_NEW
    differing = sorted(k for k in set(doc) | set(changed) if doc.get(k) != changed.get(k))
    if differing != ["max_tokens"]:
        raise ValueError(f"只允许改 max_tokens，实际改动：{differing}")
    return json.dumps(changed, ensure_ascii=False).encode("utf-8")


def check_payload_sha(raw: bytes, expected: str, name: str) -> str:
    actual = sha256_hex(raw)
    if actual != expected:
        raise ValueError(f"{name} 的 SHA256 不符：期望 {expected}，实际 {actual}")
    return actual


def parse_sse_line(line: str) -> tuple[str, Any]:
    """返回 ("done", None)、("chunk", dict) 或 ("skip", None)。只认 data: 行。"""
    text = line.strip()
    if not text.startswith("data:"):
        return ("skip", None)
    payload = text[len("data:"):].strip()
    if payload == "[DONE]":
        return ("done", None)
    return ("chunk", json.loads(payload))


def classify_chunk(chunk: dict) -> dict:
    """首 token 与非空增量只认 reasoning_content 或 content 非空；tool_calls 单独记，不计入（同任务 A2）。"""
    nonempty = False
    tool_calls = False
    finish = None
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        if delta.get("reasoning_content") or delta.get("content"):
            nonempty = True
        if delta.get("tool_calls"):
            tool_calls = True
        if choice.get("finish_reason"):
            finish = choice["finish_reason"]
    usage = None
    raw_usage = chunk.get("usage")
    if raw_usage:
        details = raw_usage.get("prompt_tokens_details") or {}
        usage = {"prompt_tokens": raw_usage.get("prompt_tokens"),
                 "completion_tokens": raw_usage.get("completion_tokens"),
                 "cached_tokens": int(details.get("cached_tokens") or 0)}
    return {"nonempty": nonempty, "tool_calls": tool_calls, "error": chunk.get("error"),
            "finish_reason": finish, "usage": usage}


def parse_prefill_lines(text: str) -> list[dict]:
    """serve.log 中的 Prefill batch 行，按出现顺序。"""
    return [{"new_seq": int(a), "new_token": int(b), "cached_token": int(c)}
            for a, b, c in PREFILL_LINE_RE.findall(text)]


def max_gap(times: Sequence[float], lo: float, hi: float) -> float | None:
    """[lo, hi] 内相邻两个非空增量时刻的最大间隔；不足两个时返回 None。"""
    inside = sorted(t for t in times if lo <= t <= hi)
    if len(inside) < 2:
        return None
    return max(b - a for a, b in zip(inside, inside[1:]))


def zero_output_count(times: Sequence[float], t_d: float, t_f: float, timing: Timing) -> int:
    """(t_d + 0.4, t_f − 0.2) 开区间内 A 的非空增量个数（区间为空时为 0）。"""
    lo, hi = t_d + timing.zero_lead_s, t_f - timing.zero_trail_s
    return sum(1 for t in times if lo < t < hi)


def in_band(value: float | None, band: tuple[float, float]) -> bool:
    return value is not None and band[0] <= value <= band[1]


def structure(lines: Sequence[dict], segments: Sequence[int], cached: int) -> dict:
    """一级：Prefill 行数等于段数。二级：一级成立，且每行 new-token 等于对应段长，
    首行 cached-token 等于预期，其余行为 0（生产日志的 cached 只记在首段，见 window02 记录）。"""
    level1 = len(lines) == len(segments)
    new_tokens = [int(line["new_token"]) for line in lines]
    cached_seen = [int(line["cached_token"]) for line in lines]
    level2 = (level1 and new_tokens == list(segments) and bool(cached_seen)
              and cached_seen[0] == cached and all(c == 0 for c in cached_seen[1:]))
    return {"level1": level1, "level2": level2, "new_tokens": new_tokens, "cached_seen": cached_seen,
            "segments_expected": list(segments), "cached_expected": cached}


def contamination_reasons(samples: Sequence[dict], t_d: float, t_after: float,
                          before_completed: int | None, after_completed: int | None,
                          our_completions: int) -> list[str]:
    """混入规则（预登记 gates.contamination）：事件期间任一读数 active 大于我方在途数，
    或事件前后 completed 之差不等于我方在该区间完成的请求数。缺读数时记为 unverified。"""
    reasons: list[str] = []
    for sample in samples:
        if "active" not in sample or not (t_d <= sample["t"] <= t_after):
            continue
        if sample["active"] > sample["ours"]:
            reasons.append(f"active {sample['active']} > ours {sample['ours']} at {sample['t']:.3f}")
            break
    if before_completed is None or after_completed is None:
        reasons.append("unverified：缺少事件前后的 completed 读数")
    elif after_completed - before_completed != our_completions:
        reasons.append(f"completed 差 {after_completed - before_completed} != 我方完成数 {our_completions}")
    return reasons


def judge_event(ev: dict, a_times: Sequence[float], samples: Sequence[dict], timing: Timing) -> dict:
    """单事件判读。ev 含：name、status、invalid_a_ended、t_d、t_f、t_end、t_after、prefill_lines、
    before_completed、after_completed、our_completions、segments、cached、band、pred。"""
    structure_info = structure(ev["prefill_lines"], ev["segments"], ev["cached"])
    t_d, t_f = ev.get("t_d"), ev.get("t_f")
    band = timing.band(ev["band"])
    gap = None
    zero = None
    if t_d is not None and t_f is not None:
        gap = max_gap(a_times, t_d - timing.margin_s, t_f + timing.margin_s)
        zero = zero_output_count(a_times, t_d, t_f, timing)
    reasons: list[str] = []
    if t_d is not None and ev.get("t_after") is not None:
        reasons = contamination_reasons(samples, t_d, ev["t_after"], ev.get("before_completed"),
                                        ev.get("after_completed"), ev.get("our_completions", 1))
    verified = not any(r.startswith("unverified") for r in reasons)
    if ev.get("status") != "ok":
        label = "请求错误（停窗）" if ev.get("status") != "aborted" else "中止（监视触发）"
    elif ev.get("invalid_a_ended"):
        label = "invalid_a_ended（不补测）"
    elif reasons and not verified:
        label = "unverified（不进入判读）"
    elif reasons:
        label = "contaminated"
    elif not structure_info["level1"]:
        label = "一级不符：只报告"
    else:
        label = "进入停顿判读"
    entered = label == "进入停顿判读"
    return {
        "name": ev["name"], "status": ev.get("status"), "label": label, "entered": entered,
        "invalid_a_ended": bool(ev.get("invalid_a_ended")), "contamination": reasons,
        "structure": structure_info, "pred_s": ev["pred"], "band_s": [band[0], band[1]],
        "G_s": gap, "G_over_P": None if gap is None or not ev["pred"] else gap / ev["pred"],
        "in_band": in_band(gap, band) if entered else None, "zero_output": zero,
        "t_d": t_d, "t_f": t_f, "t_end": ev.get("t_end"),
        "gpu_before_mib": ev.get("gpu_before_mib"), "gpu_after_mib": ev.get("gpu_after_mib"),
    }


def aggregate_verdict(n: int, k: int) -> str:
    """§7 总判：k ≥ ceil(11n/13) 成立；k ≤ floor(6n/13) 不成立；其余部分成立；n < 9 只报告不判。"""
    if n < MIN_N_FOR_JUDGMENT:
        return "只报告不判"
    if k >= math.ceil(11 * n / 13):
        return "成立"
    if k <= math.floor(6 * n / 13):
        return "不成立"
    return "部分成立"


def aggregate(judged: Sequence[dict]) -> dict:
    entered = [e for e in judged if e["entered"]]
    n = len(entered)
    k = sum(1 for e in entered if e["in_band"])
    return {"n": n, "k": k, "verdict": aggregate_verdict(n, k),
            "threshold_success_k": math.ceil(11 * n / 13) if n else None,
            "threshold_failure_k": math.floor(6 * n / 13) if n else None}
