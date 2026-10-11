"""Soak sampler v2: resumes at i=1, hard per-sample timeout via thread join,
logs to file (no pipe to block on), unbuffered appends.
Usage: python3 soak_ws2.py   (runs 15 more samples x 900s)
"""
import json, time, urllib.request, threading

URL = "http://172.16.108.9:8095"
OUT = "soak_ws.jsonl"
LOG = "soak_ws2.log"
INTERVAL = 900
START, N = 1, 16
HARD_TIMEOUT = 420


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def post(path, payload, timeout):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def sample(i):
    box = {}
    def work():
        t0 = time.time()
        try:
            d = post("/v1/chat/completions", {
                "model": "Qwen3.8-Flash-Next-NVFP4",
                "messages": [{"role": "user",
                              "content": "Write a Python quicksort function with a test."}],
                "max_tokens": 256, "temperature": 0,
                "reasoning_effort": "off"}, timeout=300)
            dt = time.time() - t0
            box["r"] = (dt, d.get("usage", {}).get("completion_tokens", 0),
                        len(d["choices"][0]["message"].get("content") or ""), None)
        except Exception as e:
            box["r"] = (time.time() - t0, 0, 0, repr(e)[:200])
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(HARD_TIMEOUT)
    if "r" not in box:
        dt, comp, clen, err = HARD_TIMEOUT, 0, 0, "HARD_TIMEOUT"
    else:
        dt, comp, clen, err = box["r"]
    try:
        st = json.loads(urllib.request.urlopen(URL + "/v1/stats", timeout=30).read())
    except Exception as e:
        st = {"error": repr(e)[:200]}
    rec = {"i": i, "ts": time.strftime("%H:%M:%S"), "total_s": round(dt, 2),
           "comp": comp, "e2e_tps": round(comp / dt, 2) if dt > 0 and comp else 0,
           "content_len": clen, "err": err,
           "stats": st if isinstance(st, dict) else str(st)[:300]}
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    log(f"i={i} tps={rec['e2e_tps']} err={err}")
    return rec


if __name__ == "__main__":
    log("sampler v2 start")
    for i in range(START, N):
        sample(i)
        if i < N - 1:
            time.sleep(INTERVAL)
    log("sampler v2 done")
