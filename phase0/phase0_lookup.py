"""S0 proxy: prompt-lookup draft acceptance upper bound, black-box vs live 8095.

Oracle simulation on server greedy output (word-level proxy):
at each position, longest prior match of the upcoming span (n>=3 words)
in prompt+generated prefix counts as a draft hit.
Reports hit rate per prompt class. No server disturbance (plain HTTP).
"""
import json, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"

PROMPTS = [
    ("code", "Write a Python quicksort function with a test, then write mergesort too:"),
    ("code", "Implement a thread-safe LRU cache in Python with get and put:"),
    ("math", "Solve: sum of first 100 primes. Show steps:"),
    ("reason", "Explain why the sky is blue, then why sunsets are red:"),
]

def complete(prompt, max_tokens=256):
    p = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
         "max_tokens": max_tokens, "temperature": 0, "reasoning_effort": "low"}
    r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    m = json.loads(urllib.request.urlopen(r, timeout=300).read())["choices"][0]["message"]
    return (m.get("reasoning_content") or "") + "\n" + (m.get("content") or "")

def hit_rate(context, gen, n_min=3, gamma=4):
    ctx, g = context.split(), gen.split()
    stream = ctx + g
    hits = tot = 0
    for i in range(len(ctx), len(stream)):
        tot += 1
        window = stream[max(0, i - 64):i]
        best = 0
        cand = stream[i:i + gamma]
        for n in range(min(gamma, len(stream) - i), n_min - 1, -1):
            pat = cand[:n]
            for s in range(len(window) - n + 1):
                if window[s:s + n] == pat:
                    best = n
                    break
            if best:
                break
        if best >= n_min:
            hits += 1
    return hits / max(tot, 1)

if __name__ == "__main__":
    for cls, pr in PROMPTS:
        try:
            out = complete(pr)
            gen = out.split("\n", 1)[1] if "\n" in out else out
            print(f"[{cls}] words={len(gen.split())} lookup-hit~{hit_rate(pr, gen):.2f}")
        except Exception as e:
            print(f"[{cls}] ERROR {e}")
