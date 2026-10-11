"""Read-only ABBA analysis of op-hak task A2 window02 against PREREG_TASK_A.json (T2 rows)."""
import json
import statistics as st
from pathlib import Path

W = Path("/data2/FreeToken/runs/dev_ophak_task_a2_20261011/window02/window")
PRE = json.loads(Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_A.json").read_text())
ROWS = PRE["trajectories"]["T2"]["rounds"]
ARMS = {"on": ("A1_on", "A2_on"), "off": ("B1_off", "B2_off")}
rec = {}
for svcs in ARMS.values():
    for s in svcs:
        rec[s] = {json.loads(l)["key"]: json.loads(l) for l in (W / s / "requests.jsonl").read_text().splitlines()}

g1_bad, drift_bad = [], []
changed, unchanged = [], []
print("round class    A1     A2     B1     B2   dON   dOFF   delta  G3on G3off")
for r in ROWS:
    k = f"T2/{r['round']:02d}"
    t = {s: rec[s][k]["ttft_s"] for s in rec}
    for arm, svcs in ARMS.items():
        exp = r["on_segments" if arm == "on" else "off_segments"]
        for s in svcs:
            d = rec[s][k]
            segs = [x["new_token"] for x in d["prefill_lines"]]
            if d["status"] != "ok" or segs != exp or d["usage"]["cached_tokens"] != r["cached"] or d["usage"]["prompt_tokens"] != r["prompt_tokens"]:
                g1_bad.append((s, k, d["status"], segs, exp))
    don = abs(t["A1_on"] - t["A2_on"]) / max(t["A1_on"], t["A2_on"])
    doff = abs(t["B1_off"] - t["B2_off"]) / max(t["B1_off"], t["B2_off"])
    if don > 0.10 or doff > 0.10:
        drift_bad.append(k)
    delta = (t["A1_on"] + t["A2_on"]) / 2 - (t["B1_off"] + t["B2_off"]) / 2
    g3on = rec["A1_on"][k]["output_sha256"] == rec["A2_on"][k]["output_sha256"]
    g3off = rec["B1_off"][k]["output_sha256"] == rec["B2_off"][k]["output_sha256"]
    print(f"{k} {r['class']:9s} {t['A1_on']:6.3f} {t['A2_on']:6.3f} {t['B1_off']:6.3f} {t['B2_off']:6.3f} {don:5.1%} {doff:5.1%} {delta:+6.3f} {g3on!s:5s} {g3off!s:5s}")
    if r["class"] == "changed":
        changed.append(delta)
    elif r["class"] == "unchanged":
        unchanged.append(delta)

print("\nG1 mismatches:", g1_bad or "none (48/48)")
print(f"G2 changed: median {st.median(changed):.3f} s, min {min(changed):.3f}, max {max(changed):.3f} (n={len(changed)})")
print(f"G2 negative control: median {st.median(unchanged):+.3f} s (n={len(unchanged)})")
print("G2 drift rounds >10%:", drift_bad or "none")
g4 = sum(rec["A1_on"][f"T2/{r['round']:02d}"]["output_sha256"] == rec["B1_off"][f"T2/{r['round']:02d}"]["output_sha256"] for r in ROWS)
print(f"G4 ON vs OFF identical outputs (A1 vs B1): {g4}/12")
print("\nmemory (MiB) before->after per service, warm-up excluded:")
for s in rec:
    mem = [(rec[s][k]["memory_before_mib"], rec[s][k]["memory_after_mib"]) for k in sorted(rec[s]) if k.startswith("T2")]
    print(f"  {s}: first {mem[0]} last {mem[-1]} max_after {max(m[1] for m in mem if m[1] is not None)}")
