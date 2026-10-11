"""S0 token-level: prompt-lookup draft acceptance, black-box vs live 8095.

Tokenizes prompt + greedy output with the real qwen38 tokenizer;
oracle n-gram lookup (n>=8 tokens, gamma=5) over prompt+prefix.
Compares against word-level proxy from phase0_lookup.py.
"""
import json, sys, urllib.request
from tokenizers import Tokenizer

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
TOK = Tokenizer.from_file(r"D:\00.开发\2026\03-模型实验\freetoken\qwen38_tokenizer.json")

PROMPTS = [
    ("code", "Write a Python quicksort function with a test, then write mergesort too:"),
    ("boiler", "Here is my API client:\nclass Client:\n    def get_user(self, id): return self._get(f\"/users/{id}\")\n    def get_order(self, id): return self._get(f\"/orders/{id}\")\nWrite get_product, get_payment, delete_user in the same style:"),
]

def complete(prompt, max_tokens=256):
    p = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
         "max_tokens": max_tokens, "temperature": 0, "reasoning_effort": "off"}
    r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    m = json.loads(urllib.request.urlopen(r, timeout=300).read())["choices"][0]["message"]
    return m.get("content") or ""

def hit_rate(ctx_ids, gen_ids, n_min=8, gamma=5):
    stream = ctx_ids + gen_ids
    base = len(ctx_ids)
    hits = tot = 0
    for i in range(base, len(stream)):
        tot += 1
        window = stream[max(0, i - 512):i]
        cand = stream[i:i + gamma]
        ok = False
        for n in range(min(gamma, len(stream) - i), n_min - 1, -1):
            pat = cand[:n]
            for s in range(len(window) - n + 1):
                if window[s:s + n] == pat:
                    ok = True
                    break
            if ok:
                break
        hits += ok
    return hits / max(tot, 1)

if __name__ == "__main__":
    for cls, pr in PROMPTS:
        try:
            out = complete(pr)
            ctx = TOK.encode(pr).ids
            gen = TOK.encode(out).ids
            print(f"[{cls}] gen_tok={len(gen)} token-lookup-hit~{hit_rate(ctx, gen):.3f}")
        except Exception as e:
            print(f"[{cls}] ERROR {e}")
