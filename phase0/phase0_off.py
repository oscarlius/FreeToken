"""Off-gear pure baseline (thinking disabled) vs live 8095."""
import json, time, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"

def run(prompt, max_tokens, effort):
    p = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
         "max_tokens": max_tokens, "temperature": 0, "reasoning_effort": effort}
    t0 = time.time()
    r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=300).read())
    dt = time.time() - t0
    m = d["choices"][0]["message"]
    comp = d.get("usage", {}).get("completion_tokens", 0)
    return {"effort": effort, "total_s": round(dt, 2),
            "comp_tok": comp, "e2e_tps": round(comp / dt, 2),
            "reason_len": len(m.get("reasoning_content") or ""),
            "content_len": len(m.get("content") or "")}

if __name__ == "__main__":
    pr = "Write a Python quicksort function with a test."
    print(json.dumps(run(pr, 512, "off"), ensure_ascii=False))
