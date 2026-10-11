"""Save greedy reference outputs for bit-exact checks. Usage: python3 phase0_save_ref.py <tag>"""
import json, sys, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
PROMPTS = {
    "quicksort": "Write a Python quicksort function with a test.",
    "fib": "Write a Python function returning the first 20 Fibonacci numbers.",
}

def gen(prompt):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 512, "temperature": 0, "reasoning_effort": "off"}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return d["choices"][0]["message"].get("content") or ""

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "ref"
    out = {k: gen(v) for k, v in PROMPTS.items()}
    fn = f"ref_{tag}.json"
    json.dump(out, open(fn, "w"), ensure_ascii=False)
    print(f"saved {fn}: " + ", ".join(f"{k}={len(v)}ch" for k, v in out.items()))
