#!/usr/bin/env python
"""把 v4 那个「重算 1 个 token 也要 2.67 s」的首 token 地板拆开归因。
每个用例都跑两趟（第一趟建缓存、第二趟应接近全命中），两趟之差才是缓存真正省掉的部分；
另配「带 tools / 不带 tools」的同提示对照，看地板是否来自工具 schema 与消息模板。"""
import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
SEED = "/data2/FreeToken/wt/e1r003/seed_45k.txt"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "读取仓库内文件内容",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "相对路径"}},
            "required": ["path"],
        },
    },
}]


def call(text, tag, tools):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": text + "\n\n只回答：ok"}],
        "max_tokens": 8,
        "temperature": 0,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if tools:
        payload["tools"] = TOOLS
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    t_real = None
    t_wire = None
    ev = 0
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            ev += 1
            now = time.perf_counter() - t0
            if t_wire is None:
                t_wire = now
            if t_real is None and '"content"' in line and '""' not in line:
                t_real = now
    print("%-26s chars=%-6d tools=%-5s events=%-3d first_wire=%6.3f first_real=%6s total=%6.3f"
          % (tag, len(text), "Y" if tools else "N", ev, t_wire or -1,
             ("%6.3f" % t_real) if t_real else "  None", time.perf_counter() - t0), flush=True)
    return t_real


def main():
    out = sys.argv[1]
    sys.stdout = open(out, "w", buffering=1)
    raw = open(SEED, encoding="utf-8", errors="replace").read()
    small = raw[:400]
    big = raw[:20000]
    print("### 同一提示连跑两趟：第二趟应接近全命中")
    for chars, tag in ((400, "small"), (20000, "big")):
        text = raw[:chars]
        call(text, "%s pass1 (cold)" % tag, False)
        time.sleep(2)
        call(text, "%s pass2 (hit)" % tag, False)
        time.sleep(2)
    print("### 同提示 带/不带 tools")
    call(big, "big no-tools", False)
    time.sleep(2)
    call(big, "big with-tools", True)
    time.sleep(2)
    call(big, "big with-tools again", True)
    print("### 消息条数效应：同样字符量拆成 12 条")
    msgs = [{"role": "user" if i % 2 == 0 else "assistant", "content": raw[:2000]} for i in range(6)]
    msgs.append({"role": "user", "content": "只回答：ok"})
    payload = {"model": MODEL, "messages": msgs, "max_tokens": 8, "temperature": 0,
               "stream": True, "chat_template_kwargs": {"enable_thinking": False}}
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    t_real = None
    for raw_line in urllib.request.urlopen(req, timeout=900):
        line = raw_line.decode("utf-8", errors="replace").strip()
        if line.startswith("data:") and t_real is None and '"content"' in line and '""' not in line:
            t_real = time.perf_counter() - t0
    print("12 条消息（每条 2000 字符）first_real=%s" % (("%.3f" % t_real) if t_real else "None"), flush=True)
    call(small, "small after multi-msg", False)


if __name__ == "__main__":
    main()
