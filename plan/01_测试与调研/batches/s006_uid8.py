import json
import collections

def idx(p):
    return [json.loads(l) for l in open(p)]

A = idx("dump_A/index.jsonl")
B = idx("dump_B/index.jsonl")
print("A kinds", collections.Counter(r["kind"] for r in A))
print("B kinds", collections.Counter(r["kind"] for r in B))
for name, X in (("A", A), ("B", B)):
    by = collections.defaultdict(list)
    for r in X:
        by[r.get("uid")].append((r["kind"], r["length"]))
    print(name, {k: by[k] for k in sorted(by, key=lambda u: (u is None, u))})
R = json.load(open("S_A_coldfirst.json"))["rounds"]
for i, r in enumerate(R):
    print(
        "A round", i,
        "prompt", r["prompt_tokens"],
        "cached", r["cached_tokens"],
        "recomputed", r["recomputed_tokens"],
    )
