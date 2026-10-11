"""Radix prefix-cache test: same prompt twice, compare TTFT (streaming, off gear)."""
import json, time, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
PROMPT = ("You are a Python expert. " * 8) + "Write a quicksort function with a test."

def once():
    p = {"model": "Qwen3.8-Flash-Next-NVFP4",
         "messages": [{"role": "user", "content": PROMPT}],
         "max_tokens": 64, "temperature": 0, "stream": True,
         "reasoning_effort": "off"}
    t0 = time.time()
    ttft = None
    n = 0
    req = urllib.request.Request(URL, data=json.dumps(p).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        for line in r:
            s = line.decode().strip()
            if not s.startswith("data:"):
                continue
            d = s[5:].strip()
            if d == "[DONE]":
                break
            try:
                c = json.loads(d)["choices"][0]["delta"].get("content") or ""
            except Exception:
                continue
            if c:
                if ttft is None:
                    ttft = time.time() - t0
                n += 1
    return round(ttft or -1, 3), n, round(time.time() - t0, 2)

if __name__ == "__main__":
    for i in range(3):
        print(f"run{i}: TTFT/n/total =", once())
