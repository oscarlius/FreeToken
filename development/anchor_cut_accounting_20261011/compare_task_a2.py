"""Read-only: compare task A window01 records with PREREG_TASK_A.json."""
import json
import sys
from pathlib import Path

R = Path("/data2/FreeToken/runs/dev_ophak_task_a2_20261011/window02/window")
PRE = json.loads(Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_A.json").read_text())
for svc, arm in (("A1_on", "on"), ("B1_off", "off"), ("B2_off", "off"), ("A2_on", "on")):
    f = R / svc / "requests.jsonl"
    if not f.exists():
        continue
    print("=====", svc)
    for line in f.read_text().splitlines():
        d = json.loads(line)
        ttft = d.get("ttft_s")
        if d["key"].startswith("warm"):
            print("warmup", d["status"], ttft)
            continue
        tr, rd = d["key"].split("/")
        p = PRE["trajectories"][tr]["rounds"][int(rd)]
        segs = [x["new_token"] for x in d["prefill_lines"]]
        exp = p["on_segments" if arm == "on" else "off_segments"]
        cached = (d.get("usage") or {}).get("cached_tokens")
        ok = "OK" if segs == exp and cached == p["cached"] else "MISMATCH"
        t = "None" if ttft is None else f"{ttft:.3f}"
        print(f"{d['key']:13s} {d['status']:7s} ttft={t:>7s} cached={cached}/{p['cached']} segs={segs} exp={exp} {ok} {p['class']}")
