"""A2 extractive probe: table->JSON forces verbatim span copying. Measures lookup hit rate."""
import json, time, urllib.request
from tokenizers import Tokenizer

URL = "http://172.16.108.9:8095/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
tok = Tokenizer.from_file("tokenizer.json")

ROWS = [
    ("ax7q2", "us-west-2", "r6g.xlarge", "running"),
    ("bk9m4", "eu-central-1", "m7i.2xlarge", "stopped"),
    ("cz3t8", "ap-southeast-1", "c6gn.medium", "running"),
    ("dw5p1", "sa-east-1", "r7iz.large", "terminated"),
    ("eq8n6", "af-south-1", "m6a.xlarge", "running"),
]
table = "id | region | type | state\n" + "\n".join(" | ".join(r) for r in ROWS)
PROMPT = ("Convert the following table to a JSON array (keep every value exactly as shown, "
          "no commentary):\n\n" + table)


def gen(prompt, max_tokens=300):
    p = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
         "max_tokens": max_tokens, "temperature": 0, "reasoning_effort": "off"}
    r = urllib.request.Request(URL, data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=300).read())["choices"][0]["message"]["content"]


def hit_rate(ctx_ids, gen_ids, n=8, gamma=5):
    grams = set()
    for i in range(len(ctx_ids) - n + 1):
        grams.add(tuple(ctx_ids[i:i + n]))
    hits = sum(1 for i in range(len(gen_ids) - gamma + 1)
               if tuple(gen_ids[i:i + gamma]) in grams)
    denom = max(1, len(gen_ids) - gamma + 1)
    return hits / denom, len(gen_ids)


out = gen(PROMPT)
ctx_ids = tok.encode(PROMPT).ids
gen_ids = tok.encode(out).ids
hr, L = hit_rate(ctx_ids, gen_ids)
print(f"gen_tok={L} hit_rate_gamma5_n8={hr:.3f}")
print(out[:400])
