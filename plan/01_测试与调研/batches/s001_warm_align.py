import json, re
d0 = [json.loads(l) for l in open("d0_prefill.jsonl")][:34]
pat = re.compile(r"Prefill batch.*#new-token: (\d+), #cached-token: (\d+)")
lines = [m for m in (pat.search(x) for x in open("warm/serve.log", errors="replace")) if m]
print("prefill_lines", len(lines), "d0", len(d0))
assert len(d0) == len(lines) - 1, "ALIGN-FAIL"
for i, (m, r) in enumerate(zip(lines, d0)):
    L = r["layers"]
    print("i=%2d new=%5s cached=%6s wall=%.3f h2d=%.2f d2d=%.2f copy=%.0f compute=%.0f d2d_ms=%.0f" % (
        i, m.group(1), m.group(2), r["wall_s"], r["h2d_gib"], r["d2d_gib"],
        sum(x["copy_ms"] for x in L), sum(x["compute_ms"] for x in L), sum(x.get("d2d_ms", 0) for x in L)))
