"""Independent judgement of task B from raw window records (main session; does not import op-hak's analyzer).

Usage: python3 -I analyze_task_b_indep.py <window_dir> <PREREG_TASK_B_v2.json>
window_dir/<SVC>/requests.jsonl and outputs.json for SVC in R0, C_A1, C_B1, C_B2, C_A2.
Gates (PREREG_TASK_B_v2): T16-lite, G1, G2 changed / unchanged, drift, G3, G5; cold rounds report only.
"""
import json
import statistics
import sys
from pathlib import Path

ARM = {"R0": "on", "C_A1": "on", "C_A2": "on", "C_B1": "thresh", "C_B2": "thresh"}
A_SVCS, B_SVCS = ("C_A1", "C_A2"), ("C_B1", "C_B2")


def traj_name(raw: str):
    low = raw.lower()
    return "seed_real" if low.startswith("seed") else "T2" if low.startswith("t2") else None


def load(window: Path, svc: str):
    d = window / svc
    recs, outs, dead = {}, {}, None
    if (d / "requests.jsonl").exists():
        for line in (d / "requests.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            t = traj_name(r.get("trajectory") or r["key"].split("/")[0])
            if t is None:
                continue
            recs[(t, int(r["round"]))] = r
            if r.get("status") in ("oom", "worker_exit") and dead is None:
                dead = (r["key"], r["status"])
    if (d / "outputs.json").exists():
        for k, v in json.loads((d / "outputs.json").read_text(encoding="utf-8")).items():
            t = traj_name(k.split("/")[0])
            if t is not None:
                outs[(t, int(k.split("/")[1]))] = v
    return recs, outs, dead


def first_diff(a: str, b: str):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def main() -> None:
    window, prereg = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    spec = {(t, r["round"]): r for t, rows in prereg["trajectories"].items() for r in rows}
    data = {s: load(window, s) for s in ARM}
    out = {"services": {s: {"rounds": len(data[s][0]), "death": data[s][2]} for s in ARM}}

    g1 = []
    for svc, arm in ARM.items():
        for key, rec in data[svc][0].items():
            exp_seg = spec[key]["on_segments" if arm == "on" else "thresh_segments"]
            lines = rec.get("prefill_lines") or []
            seg = [x["new_token"] for x in lines]
            cached = lines[0]["cached_token"] if lines else None
            if rec.get("status") == "ok" and (seg != exp_seg or cached != spec[key]["cached"]):
                g1.append({"svc": svc, "key": key, "seg": seg, "exp": exp_seg, "cached": cached, "exp_cached": spec[key]["cached"]})
    out["G1_mismatches"] = g1

    t16 = []
    for key in spec:
        r0, c1 = data["R0"][0].get(key), data["C_A1"][0].get(key)
        if r0 is None or c1 is None:
            t16.append({"key": key, "missing": True})
            continue
        same_seg = [x["new_token"] for x in r0["prefill_lines"]] == [x["new_token"] for x in c1["prefill_lines"]]
        same_out = data["R0"][1].get(key) == data["C_A1"][1].get(key)
        if not (same_seg and same_out):
            t16.append({"key": key, "same_seg": same_seg, "same_out": same_out,
                        "first_diff": first_diff(data["R0"][1].get(key, ""), data["C_A1"][1].get(key, ""))})
    out["T16_lite"] = {"pass": not t16, "diffs": t16}

    def ttft(svcs, key):
        v = [data[s][0][key]["ttft_s"] for s in svcs
             if key in data[s][0] and data[s][0][key].get("status") == "ok" and data[s][0][key].get("ttft_s") is not None]
        return v

    rows, drift = [], []
    for key, s in sorted(spec.items()):
        a, b = ttft(A_SVCS, key), ttft(B_SVCS, key)
        d = None if not a or not b else statistics.mean(a) - statistics.mean(b)
        rows.append({"key": key, "class": s["class"], "A": [round(x, 3) for x in a], "B": [round(x, 3) for x in b],
                     "delta": None if d is None else round(d, 3)})
        for arm_svcs in (A_SVCS, B_SVCS):
            v = ttft(arm_svcs, key)
            if len(v) == 2 and abs(v[0] - v[1]) / max(v) > 0.10:
                drift.append({"key": key, "arm": arm_svcs, "v": [round(x, 3) for x in v]})
    out["rows"] = rows
    out["drift"] = {"count": len(drift), "items": drift, "g2_reference_only": len(drift) > 3}

    ch = [r["delta"] for r in rows if r["class"] == "changed" and r["delta"] is not None]
    if ch:
        med = statistics.median(ch)
        verdict = "成立" if 2.3 <= med <= 3.0 and min(ch) >= 1.8 else "不成立" if med < 1.0 else "部分成立"
        out["G2_changed"] = {"n": len(ch), "median": round(med, 3), "min": round(min(ch), 3), "verdict": verdict}
    un = [r["delta"] for r in rows if r["class"] == "unchanged" and r["delta"] is not None]
    if un:
        med = statistics.median(un)
        out["G2_unchanged"] = {"n": len(un), "median": round(med, 3), "verdict": "成立" if abs(med) <= 0.3 else "不成立"}
    out["cold_report_only"] = [r for r in rows if r["class"].startswith("cold")]

    g3 = []
    for svcs in (A_SVCS, B_SVCS):
        for key in spec:
            x, y = data[svcs[0]][1].get(key), data[svcs[1]][1].get(key)
            if x is not None and y is not None and x != y:
                g3.append({"arm": svcs, "key": key, "first_diff": first_diff(x, y)})
    out["G3_diffs"] = g3
    deaths_b = {s: data[s][2] for s in B_SVCS if data[s][2]}
    out["G5"] = {"pass": not deaths_b and all(len(data[s][0]) == len(spec) for s in B_SVCS), "b_deaths": deaths_b}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
