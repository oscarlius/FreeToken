#!/usr/bin/env python
"""每请求固定开销探针：短提示与长提示各测一次流式 TTFT，用来判断回放里那个约 2.68 s 的首 token 地板
是「每请求固定成本」还是「随提示长度走」。"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
SEED = "/data2/FreeToken/wt/e1r003/seed_45k.txt"


def ttft(text, tag):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": text + "\n\n只回答：ok"}],
        "max_tokens": 4,
        "temperature": 0,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    first = None
    n = 0
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            if not line.startswith(b"data:"):
                continue
            if first is None:
                first = time.perf_counter() - t0
            n += 1
    print("%-14s chars=%-7d events=%-3d ttft=%.3f total=%.3f" % (tag, len(text), n, first or -1, time.perf_counter() - t0), flush=True)


def main():
    out = sys.argv[1]
    sys.stdout = open(out, "w", buffering=1)
    raw = open(SEED, encoding="utf-8", errors="replace").read()
    for chars, tag in ((40, "short"), (6000, "mid"), (20000, "long")):
        ttft(raw[:chars], tag)
        time.sleep(3)


if __name__ == "__main__":
    main()
