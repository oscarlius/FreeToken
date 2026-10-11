"""B-burst: 20 consecutive off-gear prompts, per-req timing + error capture."""
import json, time, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
PROMPTS = [
    "Write a Python quicksort function with a test.",
    "Write a Python binary search function with a test.",
    "Write a Python fibonacci function with a test.",
    "Write a Python mergesort function with a test.",
]
N = 20
out = []
for i in range(N):
    p = {"model": "Qwen3.8-Flash-Next-NVFP4",
         "messages": [{"role": "user", "content": PROMPTS[i % len(PROMPTS)]}],
         "max_tokens": 512, "temperature": 0, "reasoning_effort": "off"}
    t0 = time.time()
    try:
        r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                                   headers={"Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(r, timeout=300).read())
        dt = time.time() - t0
        c = d.get("usage", {}).get("completion_tokens", 0)
        out.append({"i": i, "ok": True, "s": round(dt, 2), "tok": c,
                    "tps": round(c / dt, 2)})
    except Exception as e:
        out.append({"i": i, "ok": False, "err": str(e)[:100]})
    print(out[-1], flush=True)
json.dump(out, open("burst_ws.json", "w"))
oks = [r["tps"] for r in out if r.get("ok")]
print(f"ok={len(oks)}/{N} mean={sum(oks)/len(oks):.2f} min={min(oks):.2f} max={max(oks):.2f}" if oks else "ALL FAILED")
