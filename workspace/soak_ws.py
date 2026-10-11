"""4h soak sampler for B-module (WS=1) on 8095. Run in background:
   python3 soak_ws.py  (samples every 15 min x16, appends soak_ws.jsonl)
Each sample: off-baseline (quicksort/256tok) + /v1/stats snapshot.
Accept: e2e_tps decay <5% vs pre-soak ref; no errors; TTFT stable.
"""
import json, time, urllib.request

URL = "http://172.16.108.9:8095"
OUT = "soak_ws.jsonl"
INTERVAL = 900
N = 16

def post(path, payload):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())

def sample(i):
    t0 = time.time()
    err = None
    try:
        d = post("/v1/chat/completions", {
            "model": "Qwen3.8-Flash-Next-NVFP4",
            "messages": [{"role": "user", "content": "Write a Python quicksort function with a test."}],
            "max_tokens": 256, "temperature": 0, "reasoning_effort": "off"})
        dt = time.time() - t0
        comp = d.get("usage", {}).get("completion_tokens", 0)
        content_len = len(d["choices"][0]["message"].get("content") or "")
    except Exception as e:
        dt, comp, content_len, err = time.time() - t0, 0, 0, repr(e)[:200]
    try:
        st = json.loads(urllib.request.urlopen(URL + "/v1/stats", timeout=30).read())
    except Exception as e:
        st = {"error": repr(e)[:200]}
    rec = {"i": i, "ts": time.strftime("%H:%M:%S"), "total_s": round(dt, 2),
           "comp": comp, "e2e_tps": round(comp / dt, 2) if dt > 0 and comp else 0,
           "content_len": content_len, "err": err,
           "stats": st if isinstance(st, dict) else str(st)[:300]}
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec, flush=True)
    return rec

if __name__ == "__main__":
    for i in range(N):
        sample(i)
        if i < N - 1:
            time.sleep(INTERVAL)
