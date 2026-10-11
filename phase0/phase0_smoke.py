"""Phase 0 baseline anchor: Qwen3.8-Flash-Next-NVFP4 @8095 (thinking server).

Server forces thinking mode; max_tokens must cover reasoning + answer.
Anchor (2026-09-27, greedy, reasoning_effort=low, quicksort/512):
  total_s=20.92, completion=511 tok => ~24.4 tok/s e2e, content_len=949
"""
import json, time, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
PROMPT = "Write a Python quicksort function with a test."

def run(max_tokens=512):
    payload = {"model": MODEL,
               "messages": [{"role": "user", "content": PROMPT}],
               "max_tokens": max_tokens, "temperature": 0,
               "reasoning_effort": "low"}
    t0 = time.time()
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=300).read())
    dt = time.time() - t0
    u = d.get("usage", {})
    m = d["choices"][0]["message"]
    comp = u.get("completion_tokens", 0)
    return {"total_s": round(dt, 2), "e2e_tps": round(comp / dt, 2),
            "usage": u, "content_len": len(m.get("content") or ""),
            "reason_len": len(m.get("reasoning_content") or "")}

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1))
