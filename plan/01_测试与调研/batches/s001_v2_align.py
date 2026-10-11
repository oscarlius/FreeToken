import json, re, sys
d0 = [json.loads(l) for l in open(sys.argv[1])]
segs, cur = [], []
for r in d0:
    if cur and r["chunk"] <= cur[-1]["chunk"]:
        segs.append(cur); cur = []
    cur.append(r)
segs.append(cur)
logs = sys.argv[2:]
print("D0_PROCESSES", len(segs), [len(s) for s in segs], "LOGS", len(logs))
if len(segs) != len(logs):
    print("ALIGN-FAIL process count"); sys.exit(3)
pat = re.compile(r"Prefill batch.*#new-token: (\d+), #cached-token: (\d+)")
for lg, seg in zip(logs, segs):
    lines = [m for m in (pat.search(x) for x in open(lg, errors="replace")) if m]
    print("PROC", lg, "prefill_lines", len(lines), "d0_records", len(seg))
    if len(seg) != len(lines) - 1:
        print("ALIGN-FAIL count", lg); continue
    for i, (m, r) in enumerate(zip(lines, seg)):
        new, cached = int(m.group(1)), int(m.group(2))
        if new <= 64:
            L = r["layers"]
            print("SEG i=%d new=%d cached=%d wall_s=%.3f h2d_gib=%.2f d2d_gib=%.2f total_gib=%.2f sum_copy_ms=%.0f sum_compute_ms=%.0f sum_d2d_ms=%.0f med_compute_ms=%.2f" % (
                i, new, cached, r["wall_s"], r["h2d_gib"], r["d2d_gib"], r["h2d_gib"] + r["d2d_gib"],
                sum(x["copy_ms"] for x in L), sum(x["compute_ms"] for x in L), sum(x.get("d2d_ms", 0) for x in L),
                sorted(x["compute_ms"] for x in L)[len(L) // 2]))
