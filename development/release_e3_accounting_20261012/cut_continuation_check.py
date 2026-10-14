"""Detect anchor-cut continuation rows in a serve.log without request ids (CPU only, read-only).

Signature (task B C_A1, cut on): a cut request logs its first segment and, in the same scheduling burst,
a continuation Prefill row with #new-seq 1, #cached-token 0, same #running-req, adjacent in the log.
A new request instead shows the previous request decoding / the scheduler idling / its own POST line first.

Two levels:
  strict - the two Prefill rows are adjacent lines (nothing in between);
  loose  - only "Decode batch" lines in between (covers task S's interleaved decode under concurrency).
Under e3 a cut is legal only when the request's remaining prefill exceeds 32768, i.e. first + continuation > 32768.

Usage: python3 -I cut_continuation_check.py LOG [LOG ...]
"""
import re
import sys
from datetime import datetime

MIN_TOKENS = 32768
MAX_GAP_S = 15
ANSI = re.compile(r"\x1b\[[0-9;]*m")
PREFILL = re.compile(r"\[(\d{4}-\d{2}-\d{2})\|(\d{2}:\d{2}:\d{2})\|.*Prefill batch, #new-seq: (\d+), #new-token: (\d+), "
                     r"#cached-token: (\d+).*?#running-req: (\d+)")


def classify(path: str) -> dict:
    lines = [ANSI.sub("", s) for s in open(path, encoding="utf-8", errors="replace").read().splitlines()]
    rows = []
    for i, text in enumerate(lines):
        m = PREFILL.search(text)
        if m:
            rows.append({"i": i, "at": datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S"),
                         "seq": int(m.group(3)), "new": int(m.group(4)), "cached": int(m.group(5)),
                         "running": int(m.group(6))})
    found = {"strict": [], "loose": []}
    for a, b in zip(rows, rows[1:]):
        if not (a["seq"] == 1 and b["seq"] == 1 and b["cached"] == 0 and b["running"] == a["running"]
                and (b["at"] - a["at"]).total_seconds() <= MAX_GAP_S):
            continue
        between = [s for s in lines[a["i"] + 1:b["i"]] if s.strip()]
        level = "strict" if not between else "loose" if all("Decode batch" in s for s in between) else None
        if level:
            found[level].append({"line": a["i"] + 1, "at": a["at"].strftime("%H:%M:%S"), "new": (a["new"], b["new"]),
                                 "first_cached": a["cached"], "remain": a["new"] + b["new"]})
    summary = {"prefill_rows": len(rows)}
    for level, pairs in found.items():
        summary[level] = {"pairs": len(pairs), "le_32768": sum(p["remain"] <= MIN_TOKENS for p in pairs),
                          "gt_32768": sum(p["remain"] > MIN_TOKENS for p in pairs),
                          "le_examples": [p for p in pairs if p["remain"] <= MIN_TOKENS][:5]}
    return summary


if __name__ == "__main__":
    for log in sys.argv[1:]:
        print(log.split("/")[-2], classify(log))
