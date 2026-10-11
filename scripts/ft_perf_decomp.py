#!/usr/bin/env python3
"""FreeToken P0 性能分解与回归测试框架（二次开发第一步，不动推理代码）。

口径（与研究报告第 2 章一致）：
- TTFT：发出请求 -> 第一条带正文的 delta.content 事件（客户端可见首 token）。
- 解码：(completion_tokens - 1) / (t_last - t_first)，至少 2 个正文事件。
- 并发总吞吐：窗口内所有请求 completion_tokens 之和 / 窗口墙钟。
- token 间隔：相邻正文事件间隔的 p50/p95/max（并发调度验收用）。

fixtures（研究报告 9.2 必测场景）：
- cold_long   全新长输入，唯一前缀，期望 cached_tokens == 0
- repeat      完全重复请求，跑 2 遍，第 2 遍期望 cached_tokens > 0
- tail_append 尾部追加：共享长前缀 + 短新后缀，期望命中且只算后缀
- short       健康短提示冒烟（回归守门）
- conc2/conc4 并发：多路同时生成，记单路速度 + 总吞吐 + 间隔分布

用法：
  python3 ft_perf_decomp.py check [--url ...] [--model-dir ...]
  python3 ft_perf_decomp.py run --fixture cold_long --out runs/x.jsonl [--repeat 3]
  python3 ft_perf_decomp.py compare --baseline base.jsonl --current cur.jsonl

依赖：仅 stdlib + transformers（tokenizer）。推理服务只用 8095。
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None

MODEL = "Qwen3.8-Flash-Next-NVFP4"
MODEL_DIR = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
URL = "http://127.0.0.1:8095/v1/chat/completions"
GPU_LOCK = "/data2/_shared/gpu.lock"

UNIT = "模型验收记录：在某台24GB显存的机器上，对一个48层、512路由专家、每token激活10个专家的混合专家模型做端到端编码代理评测。工具调用必须可解析，修改必须落到指定文件与指定位置，隐藏测试不得被模型看到，收尾必须由模型自己声明。\n"
TAIL = "\n请基于以上材料逐条展开，写一段不少于3000字的详细技术论述，不要提前结束。"
SHORT_PROMPT = "用三句话介绍混合专家模型的前缀缓存。"


def build_long(tok, target, prefix):
    head_ids = tok.encode(prefix + "\n请基于以下长文本材料回答。\n", add_special_tokens=False)
    tail_ids = tok.encode(TAIL, add_special_tokens=False)
    unit_ids = tok.encode(UNIT, add_special_tokens=False) or tok.encode("padding ", add_special_tokens=False)
    reps = max(1, (target - len(head_ids) - len(tail_ids)) // len(unit_ids)) + 2
    ids = (head_ids + unit_ids * reps)[: max(1, target - len(tail_ids))] + tail_ids
    ids = ids[:target]
    return tok.decode(ids, skip_special_tokens=True), len(ids)


def post_stream(url, payload, timeout=1800):
    """返回 (send_t, [event_t...], usage, finish)。event_t 为正文事件时刻。"""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    events = []
    texts = []
    usage, finish = None, None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            p = line[5:].strip()
            if p == "[DONE]":
                break
            try:
                evt = json.loads(p)
            except json.JSONDecodeError:
                continue
            if evt.get("usage"):
                usage = evt["usage"]
            for ch in evt.get("choices") or []:
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    events.append(time.perf_counter())
                    texts.append(delta["content"])
    return t0, events, usage or {}, finish, "".join(texts)


def summarize(t0, events, usage):
    u = usage or {}
    ptok = int(u.get("prompt_tokens") or 0)
    ctok = int(u.get("completion_tokens") or 0)
    cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    ttft = (events[0] - t0) if events else None
    decode = None
    if len(events) >= 2 and events[-1] > events[0] and ctok >= 2:
        decode = (ctok - 1) / (events[-1] - events[0])
    gaps = [b - a for a, b in zip(events, events[1:])]
    gap_stat = None
    if gaps:
        s = sorted(gaps)
        gap_stat = {
            "n": len(gaps),
            "p50": round(s[len(s) // 2], 4),
            "p95": round(s[min(len(s) - 1, int(len(s) * 0.95))], 4),
            "max": round(s[-1], 4),
        }
    return {
        "prompt_tokens": ptok,
        "cached_tokens": cached,
        "completion_tokens": ctok,
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "decode_tps": round(decode, 2) if decode else None,
        "gap_s": gap_stat,
    }


def one_request(tok, url, model, text, max_tokens, nothink, label, expect_cache):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if nothink:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    t0, events, usage, finish, full_text = post_stream(url, payload)
    wall = ((events[-1] if events else time.perf_counter()) - t0)
    m = summarize(t0, events, usage)
    m.update({
        "label": label,
        "wall_s": round(wall, 3),
        "completion_head": full_text[:200],
        "completion_text": full_text,
        "finish_reason": finish,
        "expect_cache": expect_cache,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    cached = m["cached_tokens"]
    if expect_cache == "zero":
        m["expect_ok"] = cached == 0 and m["ttft_s"] is not None
    elif expect_cache == "hit":
        m["expect_ok"] = cached > 0 and m["ttft_s"] is not None
    else:
        m["expect_ok"] = m["ttft_s"] is not None
    return m


def run_fixture(args, tok):
    rid = "s%d" % args.seed if args.seed is not None else uuid.uuid4().hex[:8]
    recs = []
    if args.fixture == "cold_long":
        if args.warmup:
            text, _ = build_long(tok, args.target, "Cold-Warmup-%s" % rid)
            one_request(tok, args.url, args.model, text, 128, True, "warmup", "zero")
            print("warmup done (discarded)")
        for i in range(args.repeat):
            text, _ = build_long(tok, args.target, "Cold-P0-%s-%d" % (rid, i))
            recs.append(one_request(tok, args.url, args.model, text, 128, True,
                                    "cold_long#%d" % i, "zero"))
    elif args.fixture == "repeat":
        text, _ = build_long(tok, args.target, "Repeat-P0-%s" % rid)
        recs.append(one_request(tok, args.url, args.model, text, 128, True, "repeat#1", "zero"))
        recs.append(one_request(tok, args.url, args.model, text, 128, True, "repeat#2", "hit"))
    elif args.fixture == "tail_append":
        prefix, _ = build_long(tok, args.target, "TailBase-P0-%s" % rid)
        recs.append(one_request(tok, args.url, args.model, prefix, 128, True, "tail_base", "zero"))
        recs.append(one_request(tok, args.url, args.model,
                                prefix + "\n补充：再用两句话总结上文要点。", 128, True,
                                "tail_append", "hit"))
    elif args.fixture == "short":
        for i in range(args.repeat):
            recs.append(one_request(tok, args.url, args.model, SHORT_PROMPT, 128, True,
                                    "short#%d" % i, "any"))
    elif args.fixture in ("conc2", "conc4"):
        n = int(args.fixture[4:])
        with ThreadPoolExecutor(max_workers=n) as ex:
            futs = [ex.submit(one_request, tok, args.url, args.model, SHORT_PROMPT,
                              128, True, "conc%d#%d" % (n, i), "any") for i in range(n)]
            recs = [f.result() for f in futs]
        tot = sum(r["completion_tokens"] for r in recs)
        walls = [r.get("wall_s", 0) for r in recs]
        recs.append({"label": "conc%d_summary" % n, "ts": recs[0]["ts"] if recs else "",
                     "total_completion_tokens": tot,
                     "window_s": round(max(walls) if walls else 0, 3),
                     "agg_tps": round(tot / max(walls), 2) if walls and max(walls) > 0 else None})
    else:
        sys.exit("unknown fixture: %s" % args.fixture)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(recs, ensure_ascii=False, indent=1))
    bad = [r.get("label") for r in recs if "expect_ok" in r and not r["expect_ok"]]
    if bad:
        print("EXPECT_FAIL: %s" % bad, file=sys.stderr)
        return 2
    return 0


def cmd_check(args):
    ok = True
    lock = os.path.exists(GPU_LOCK)
    print("gpu_lock_present=%s" % lock)
    try:
        urllib.request.urlopen(args.url.replace("/v1/chat/completions", "/v1/models"),
                               timeout=10).read(64)
        print("service_8095=UP")
    except Exception as e:
        print("service_8095=DOWN (%s: %s)" % (type(e).__name__, e))
        ok = False
    if AutoTokenizer is None:
        print("tokenizer=MISSING (pip install transformers)")
        ok = False
    else:
        try:
            tok = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
            ids = tok.encode(SHORT_PROMPT, add_special_tokens=False)
            print("tokenizer=OK short_tokens=%d" % len(ids))
        except Exception as e:
            print("tokenizer=FAIL (%s)" % e)
            ok = False
    return 0 if ok else 1


def load_jsonl(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def cmd_compare(args):
    base = [r for r in load_jsonl(args.baseline) if "expect_ok" in r]
    cur = [r for r in load_jsonl(args.current) if "expect_ok" in r]
    labels = sorted({r["label"].split("#")[0] for r in base} & {r["label"].split("#")[0] for r in cur})
    if not labels:
        print("no overlapping fixtures")
        return 2
    fails = []
    for lb in labels:
        for metric in ("ttft_s", "decode_tps"):
            bv = [r[metric] for r in base if r["label"].startswith(lb) and r.get(metric)]
            cv = [r[metric] for r in cur if r["label"].startswith(lb) and r.get(metric)]
            if not bv or not cv:
                continue
            b, c = statistics.mean(bv), statistics.mean(cv)
            if metric == "ttft_s":
                ok = c <= b * (1 + args.tol)
                detail = "ttft base=%.2f cur=%.2f (+%.1f%%, tol +%.0f%%)" % (b, c, (c - b) / b * 100, args.tol * 100)
            else:
                ok = c >= b * (1 - args.tol)
                detail = "decode base=%.2f cur=%.2f (%+.1f%%, tol -%.0f%%)" % (b, c, (c - b) / b * 100, args.tol * 100)
            print("%-18s %s %s" % (lb, "PASS" if ok else "FAIL", detail))
            if not ok:
                fails.append((lb, metric))
    bad = [r["label"] for r in cur if not r.get("expect_ok")]
    if bad:
        print("EXPECT_FAIL in current: %s" % bad)
        fails.append(("expect", bad))
    print("RESULT: %s" % ("PASS" if not fails else "FAIL %s" % fails))
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description="FreeToken P0 性能分解与回归测试")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--url", default=URL)
    c.add_argument("--model-dir", default=MODEL_DIR)
    r = sub.add_parser("run")
    r.add_argument("--fixture", required=True,
                   choices=["cold_long", "repeat", "tail_append", "short", "conc2", "conc4"])
    r.add_argument("--out", required=True)
    r.add_argument("--repeat", type=int, default=3)
    r.add_argument("--warmup", action="store_true",
                   help="cold_long 先跑 1 次不记录的暖机请求，丢弃该结果")
    r.add_argument("--target", type=int, default=32000)
    r.add_argument("--seed", type=int, default=None,
                       help="固定cold_id种子（确定性对比用），默认随机")
    r.add_argument("--url", default=URL)
    r.add_argument("--model", default=MODEL)
    r.add_argument("--model-dir", default=MODEL_DIR)
    m = sub.add_parser("compare")
    m.add_argument("--baseline", required=True)
    m.add_argument("--current", required=True)
    m.add_argument("--tol", type=float, default=0.15)
    args = ap.parse_args()
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    if AutoTokenizer is None:
        sys.exit("need transformers for tokenizer")
    tok = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    return run_fixture(args, tok)


if __name__ == "__main__":
    sys.exit(main())
