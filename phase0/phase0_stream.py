"""Stream-timing baseline: TTFT + steady decode tps, off-gear, live 8095."""
import json, time, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
pr = "Write a Python quicksort function with a test."
p = {"model": "Qwen3.8-Flash-Next-NVFP4",
     "messages": [{"role": "user", "content": pr}],
     "max_tokens": 256, "temperature": 0,
     "reasoning_effort": "off", "stream": True}
t0 = time.time()
r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                           headers={"Content-Type": "application/json"})
n = 0
t_first = None
stamps = []
with urllib.request.urlopen(r, timeout=300) as resp:
    for line in resp:
        s = line.decode().strip()
        if not s.startswith("data:"):
            continue
        if "[DONE]" in s:
            break
        try:
            d = json.loads(s[5:])
            c = d["choices"][0].get("delta", {}).get("content") or ""
        except Exception:
            continue
        if c:
            now = time.time()
            if t_first is None:
                t_first = now
            n += len(c)
            stamps.append(now)
t_end = time.time()
chars = n
print(json.dumps({
    "ttft_s": round(t_first - t0, 2),
    "total_s": round(t_end - t0, 2),
    "chars": chars,
    "steady_cps": round(chars / (t_end - t_first), 1),
    "approx_tps": round(chars / 4 / (t_end - t_first), 1)}, indent=1))
