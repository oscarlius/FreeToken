"""Independent re-judgement of task S from raw records (main session; does not import op-hak's stall_core).

Usage: python3 -I analyze_task_s.py <run_dir> <PREREG_TASK_S_v2.json>
Reads events.jsonl, a_times.json, samples.jsonl. Prints per-event table + aggregate as JSON.
Extra diagnostics beyond the prereg: B's own TTFT (t_f - t_d), where the gap starts relative to t_d,
and G - TTFT (expected about +one decode step minus tokenization).
"""
import json
import math
import sys
from pathlib import Path

ZERO_LEAD, ZERO_TRAIL = 0.4, 0.2


def jsonl(p: Path) -> list:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def gap(times: list, lo: float, hi: float):
    inside = sorted(t for t in times if lo <= t <= hi)
    if len(inside) < 2:
        return None, None
    g, start = max((b - a, a) for a, b in zip(inside, inside[1:]))
    return g, start


def main() -> None:
    run, prereg = Path(sys.argv[1]), Path(sys.argv[2])
    spec = {e["event"]: e for e in json.loads(prereg.read_text(encoding="utf-8"))["events"]}
    events = jsonl(run / "events.jsonl")
    a_times = sorted(json.loads((run / "a_times.json").read_text()))
    samples = jsonl(run / "samples.jsonl")
    rows = []
    for ev in events:
        s = spec[ev["name"]]
        t_d, t_f = ev.get("t_d"), ev.get("t_f")
        lines = ev.get("prefill_lines") or []
        lv1 = len(lines) == len(s["segments_expected"])
        lv2 = lv1 and [x["new_token"] for x in lines] == s["segments_expected"] \
            and lines[0]["cached_token"] == s["cached_expected"] and all(x["cached_token"] == 0 for x in lines[1:])
        g = g_start = None
        zero = None
        if t_d is not None and t_f is not None:
            g, g_start = gap(a_times, t_d - 2.0, t_f + 2.0)
            zero = sum(1 for t in a_times if t_d + ZERO_LEAD < t < t_f - ZERO_TRAIL)
        win = [x for x in samples if ev["t_pre"] <= x["t"] <= ev["t_after"]]
        over = [x for x in win if "active" in x and x["active"] > 2]
        dc = None if ev.get("before_completed") is None or ev.get("after_completed") is None \
            else ev["after_completed"] - ev["before_completed"]
        contaminated = bool(over) or (dc is not None and dc != ev.get("our_completions"))
        lo, hi = s["stall_band_s"]
        rows.append({
            "event": ev["name"], "status": ev.get("status"),
            "segs_obs": [x["new_token"] for x in lines], "cached_obs": lines[0]["cached_token"] if lines else None,
            "segs_exp": s["segments_expected"], "cached_exp": s["cached_expected"], "lv1": lv1, "lv2": lv2,
            "usage_cached": ((ev.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
            "P": s["prefill_pred_s"], "G": None if g is None else round(g, 3),
            "G_over_P": None if g is None else round(g / s["prefill_pred_s"], 3),
            "ttft_B": None if t_d is None or t_f is None else round(t_f - t_d, 3),
            "gap_start_after_td": None if g_start is None else round(g_start - t_d, 3),
            "in_band": g is not None and lo <= g <= hi, "band": [lo, hi], "zero_output": zero,
            "dcompleted": dc, "ours": ev.get("our_completions"), "max_active": max((x.get("active", 0) for x in win), default=None),
            "contaminated": contaminated, "invalid_a_ended": ev.get("invalid_a_ended"),
        })
    valid = [r for r in rows if r["lv1"] and not r["contaminated"] and not r["invalid_a_ended"] and r["G"] is not None]
    n, k = len(valid), sum(r["in_band"] for r in valid)
    if n < 9:
        verdict = "只报告（n < 9）"
    elif k >= math.ceil(11 * n / 13):
        verdict = "成立"
    elif k <= math.floor(6 * n / 13):
        verdict = "不成立"
    else:
        verdict = "部分成立"
    print(json.dumps({"rows": rows, "n": n, "k": k, "verdict": verdict,
                      "zero_output_events": [r["event"] for r in rows if r["zero_output"]],
                      "a_deltas": len(a_times)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
