"""A2 probe: token-level prompt-lookup hit rate on multi-turn reuse traffic.

Simulates agent loop: turn1 produces a long tool-like output, turn2/3 reuse it.
Draft pool = all prior turns' tokens (user+assistant). Oracle measures, for each
generated token, the longest match (n>=8) against the pool, greedy cover (gamma=5).
"""
import json, time, urllib.request

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"

TOOL_OUTPUT = """[tool:pytest] 47 passed, 3 failed in 12.4s
FAILED tests/models/qwen4_exp/test_moe_decode.py::test_routing_stability - assert 0.97 > 0.99
FAILED tests/models/qwen4_exp/test_moe_decode.py::test_expert_balance - std 0.041 > 0.02
FAILED tests/kvcache/test_page_reuse.py::test_evict_order - LRU order mismatch at page 17
[tool:ruff] 2 errors: fused_nvfp4.py:164 undefined name 'two_i', moe.py:88 unused import
[tool:nvidia-smi] 24054MiB / 24564MiB used, 0 running processes on GPU 0
"""

TURNS = [
    "Run the checks and paste the raw tool output below. Then summarize failures in one line. RAW:\n" + TOOL_OUTPUT,
    "Repeat the exact pytest failure lines verbatim, then explain the ruff errors.",
    "Now quote the nvidia-smi line verbatim and restate the three FAILED test names.",
]

try:
    from tokenizers import Tokenizer
    enc = Tokenizer.from_file("tokenizer.json")
    def tok(s): return enc.encode(s).ids
except Exception as e:
    print("need tokenizer.json:", e); raise SystemExit(1)


def chat(messages, max_tokens=256):
    p = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
         "temperature": 0, "reasoning_effort": "off"}
    r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=300).read())
    return d["choices"][0]["message"].get("content") or ""


def cover(gen, pool, n_min=8, gamma=5):
    cov, i, hits = 0, 0, 0
    L = len(gen)
    while i < L:
        best = 0
        win = gen[i:i + gamma]
        for n in range(min(gamma, L - i), n_min - 1, -1):
            seg = tuple(win[:n])
            for j in range(len(pool) - n + 1):
                if tuple(pool[j:j + n]) == seg:
                    best = n; break
            if best: break
        if best:
            cov += best; hits += 1; i += best
        else:
            i += 1
    return cov / max(L, 1), hits


msgs, pool = [], []
for k, t in enumerate(TURNS):
    msgs.append({"role": "user", "content": t})
    out = chat(msgs)
    g = tok(out)
    rate, hits = cover(g, pool, 8, 5)
    print(f"turn{k+1}: gen={len(g)}tok hit_rate={rate:.3f} segs={hits}")
    msgs.append({"role": "assistant", "content": out})
    pool.extend(tok(t) + g)
