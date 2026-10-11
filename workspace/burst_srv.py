"""Server-side burst: 20 consecutive off-gear prompts, one json row each.
Run: nohup python3 burst_srv.py. ~7 min."""
import json, time, urllib.request

URL = "http://127.0.0.1:8095/v1/chat/completions"
JSONL = "/data2/FreeToken/burst_ws_srv.jsonl"
LOG = "/data2/FreeToken/burst_srv.log"
N = 20

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def one(k):
    p = {"model": "Qwen3.8-Flash-Next-NVFP4",
         "messages": [{"role": "user", "content": "Write a Python quicksort function with a test."}],
         "max_tokens": 512, "temperature": 0, "reasoning_effort": "off"}
    t0 = time.time()
    try:
        r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                                   headers={"Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(r, timeout=300).read())
        dt = time.time() - t0
        c = d.get("usage", {}).get("completion_tokens", 0)
        row = {"k": k, "ok": True, "s": round(dt, 2), "tok": c,
               "e2e_tps": round(c / dt, 2)}
    except Exception as e:
        row = {"k": k, "ok": False, "err": str(e)[:160]}
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    log(f"k={k} ok={row['ok']} tps={row.get('e2e_tps')}")
    return row["ok"]

if __name__ == "__main__":
    log("burst start N=20")
    for k in range(N):
        one(k)
    log("burst done")
