#!/usr/bin/env python3
"""FreeToken 冷 32K 首 token / 解码探针（任务 TEST_TASK_FT_COLD32K_TTFT_20261002）。

口径：
- build_text 与 exllamav3/scripts/probe_32k_once.py 完全一致（唯一头 + 重复验收记录 + 固定尾）。
- 流式 POST /v1/chat/completions，stream=true，stream_options.include_usage=true。
- 首 token：发出请求 -> 第一条带正文的 delta.content 事件（不含 HTTP 响应头时刻）。
- 解码：(completion_tokens - 1) / (最后一条正文事件时刻 - 第一条正文事件时刻)。
- cached_tokens > 0 或 prompt_tokens 偏离目标几千 token 的轮次由调用方判废重测。
"""
import json
import os
import sys
import time
import urllib.request

from transformers import AutoTokenizer

MODEL = "Qwen3.8-Flash-Next-NVFP4"
MODEL_DIR = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
URL = "http://127.0.0.1:8095/v1/chat/completions"
OUT_DIR = "/data2/FreeToken/runs/cold32k_20261002"
TARGET_DEFAULT = 32052
MAX_TOKENS_DEFAULT = 128


def build_text(tok, target, cold_id):
    head = f"Cold-prefix-{cold_id}\n请基于以下长文本材料回答。\n"
    tail = "\n请基于以上材料逐条展开，写一段不少于3000字的详细技术论述，不要提前结束。"
    unit = "模型验收记录：在某台24GB显存的机器上，对一个48层、512路由专家、每token激活10个专家的混合专家模型做端到端编码代理评测。工具调用必须可解析，修改必须落到指定文件与指定位置，隐藏测试不得被模型看到，收尾必须由模型自己声明。\n"
    head_ids = tok.encode(head, add_special_tokens=False)
    tail_ids = tok.encode(tail, add_special_tokens=False)
    unit_ids = tok.encode(unit, add_special_tokens=False)
    if not unit_ids:
        unit_ids = tok.encode("padding ", add_special_tokens=False)
    reps = max(1, (target - len(head_ids) - len(tail_ids)) // len(unit_ids)) + 2
    ids = (head_ids + unit_ids * reps)[: max(1, target - len(tail_ids))] + tail_ids
    ids = ids[:target]
    return tok.decode(ids, skip_special_tokens=True), len(ids)


def main():
    cold_id = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else TARGET_DEFAULT
    max_tokens = int(sys.argv[3]) if len(sys.argv) > 3 else MAX_TOKENS_DEFAULT
    nothink = len(sys.argv) > 4 and sys.argv[4] == "nothink"

    tok = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
    text, n_tok = build_text(tok, target, cold_id)

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": text}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    # 默认模板思考模式会把 128 token 预算全部耗在 reasoning_content 上，
    # 正文 content 事件不出现，TTFT 口径无法成立；nothink 时显式关闭。
    if nothink:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )

    t0 = time.perf_counter()
    resp = urllib.request.urlopen(req, timeout=1800)
    t_first = None
    t_last = None
    usage = None
    finish = None
    content_events = 0
    reasoning_events = 0
    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if evt.get("usage"):
            usage = evt["usage"]
        choices = evt.get("choices") or []
        if not choices:
            continue
        ch = choices[0]
        if ch.get("finish_reason"):
            finish = ch["finish_reason"]
        delta = ch.get("delta") or {}
        if delta.get("reasoning_content"):
            reasoning_events += 1
            continue
        if delta.get("content"):
            now = time.perf_counter()
            if t_first is None:
                t_first = now
            t_last = now
            content_events += 1
    wall = time.perf_counter() - t0

    u = usage or {}
    ptok = int(u.get("prompt_tokens") or 0)
    ctok = int(u.get("completion_tokens") or 0)
    cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)

    ttft = (t_first - t0) if t_first is not None else None
    decode_tps = None
    if t_first is not None and t_last is not None and t_last > t_first and ctok >= 2:
        decode_tps = (ctok - 1) / (t_last - t_first)

    rec = {
        "cold_id": cold_id,
        "prompt_tokens": ptok,
        "cached_tokens": cached,
        "completion_tokens": ctok,
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "decode_tps": round(decode_tps, 2) if decode_tps else None,
        "finish_reason": finish,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{cold_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)

    diag = {
        "built_tokens": n_tok,
        "enable_thinking": not nothink,
        "content_events": content_events,
        "reasoning_events": reasoning_events,
        "wall_s": round(wall, 3),
        "cache_ok": cached == 0,
        "prompt_len_ok": abs(ptok - target) < 2000,
        "decode_ok": decode_tps is not None,
        "out_path": out_path,
    }
    print(json.dumps({"record": rec, "diag": diag}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
