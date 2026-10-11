#!/bin/env python
"""多消息 ckpt 税的 N>=3 复测：同一台服务上把「12 条消息」与「1 条消息」交替跑 5 遍，
把 batch16 里单次读数的结论做成带离散度的数。"""
import json
import statistics
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
SEED = "/data2/FreeToken/wt/e1r003/seed_45k.txt"
REPS = 5


def first_real(payload):
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    t_real = None
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            if t_real is None and '"content"' in line and '""' not in line:
                t_real = time.perf_counter() - t0
                break
    return t_real


def main():
    out = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else "arm"
    raw = open(SEED, encoding="utf-8", errors="replace").read()
    single = {"model": MODEL, "max_tokens": 4, "temperature": 0, "stream": True,
              "chat_template_kwargs": {"enable_thinking": False},
              "messages": [{"role": "user", "content": raw[:24000] + "\n\n只回答：ok"}]}
    multi_msgs = [{"role": "user" if i % 2 == 0 else "assistant", "content": raw[:2000]} for i in range(12)]
    multi_msgs.append({"role": "user", "content": "只回答：ok"})
    multi = {"model": MODEL, "max_tokens": 4, "temperature": 0, "stream": True,
             "chat_template_kwargs": {"enable_thinking": False}, "messages": multi_msgs}
    # 交替跑，消掉时段与顺序效应
    s, m = [], []
    for i in range(REPS):
        a = first_real(single)
        b = first_real(multi)
        s.append(a)
        m.append(b)
        print("rep=%d single=%.3f multi=%.3f delta=%.3f" % (i, a, b, b - a), flush=True)
        time.sleep(3)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"arm": tag, "reps": REPS, "single": s, "multi": m,
                   "single_median": statistics.median(s), "multi_median": statistics.median(m),
                   "single_spread": max(s) - min(s), "multi_spread": max(m) - min(m),
                   "delta_median": statistics.median([y - x for x, y in zip(s, m)])}, f, ensure_ascii=False, indent=2)
    print("MEDIAN single=%.3f multi=%.3f delta=%.3f spread=%.3f/%.3f" % (
        statistics.median(s), statistics.median(m),
        statistics.median([y - x for x, y in zip(s, m)]), max(s) - min(s), max(m) - min(m)), flush=True)


if __name__ == "__main__":
    main()
