"""Soak sampler v3: resume i=3..15, one row PER TICK guaranteed.
Every tick appends exactly one line (ok or err) + heartbeat to file log.
Run detached: pythonw or nohup. Never dies on a bad sample."""
import json, time, threading, urllib.request, traceback

URL = "http://172.16.108.9:8095/v1/chat/completions"
STATS = "http://172.16.108.9:8095/stats"
JSONL = "soak_ws.jsonl"
LOG = "soak_ws3.log"
TICK = 900
HARD = 420
START_I = 3
END_I = 15

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def sample_once():
    p = {"model": "Qwen3.8-Flash-Next-NVFP4",
         "messages": [{"role": "user", "content": "Write a Python quicksort function with a test."}],
         "max_tokens": 512, "temperature": 0, "reasoning_effort": "off"}
    t0 = time.time()
    r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=300).read())
    dt = time.time() - t0
    c = d.get("usage", {}).get("completion_tokens", 0)
    try:
        st = json.loads(urllib.request.urlopen(STATS, timeout=15).read())
    except Exception:
        st = {}
    return {"ok": True, "s": round(dt, 2), "tok": c,
            "e2e_tps": round(c / dt, 2), "stats": st}

def tick(i):
    box = {}
    t = threading.Thread(target=lambda: box.update({"r": sample_once()}), daemon=True)
    t.start()
    t.join(HARD)
    row = {"i": i, "ts": time.strftime("%H:%M:%S")}
    if "r" in box:
        row.update(box["r"])
    else:
        row.update({"ok": False, "err": f"hard-timeout>{HARD}s"})
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    log(f"i={i} ok={row['ok']} tps={row.get('e2e_tps')}")

def main():
    log(f"v3 start, resume i={START_I}")
    for i in range(START_I, END_I + 1):
        try:
            tick(i)
        except Exception:
            with open(JSONL, "a", encoding="utf-8") as f:
                f.write(json.dumps({"i": i, "ts": time.strftime("%H:%M:%S"),
                                    "ok": False, "err": "loop-exc"}) + "\n")
            log(f"i={i} LOOP-EXC\n{traceback.format_exc()[-500:]}")
        if i < END_I:
            time.sleep(TICK)
    log("v3 done 3..15")

if __name__ == "__main__":
    main()
