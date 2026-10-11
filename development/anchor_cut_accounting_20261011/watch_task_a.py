"""Print one line per observable state of op-hak task A window01 (read-only)."""
import json
from pathlib import Path

R = Path("/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01/window")
for name in ("A1_on", "B1_off", "B2_off", "A2_on"):
    d = R / name
    if (d / "summary.json").exists():
        s = json.loads((d / "summary.json").read_text())
        print(f"svc {name} {s['status']} {s['done']}/{s['planned']} cleanup={s.get('cleanup_ok')}")
    elif d.exists():
        print(f"svc {name} started")
    if (d / "oom_excerpt.log").exists():
        print(f"oom {name}")
if (R / "window_summary.json").exists():
    print("window " + json.loads((R / "window_summary.json").read_text())["terminal"])
if (R / "CLEANUP_BLOCKED.md").exists():
    print("CLEANUP_BLOCKED")
active = Path("/data2/FreeToken/run/production.active.json")
if active.exists():
    try:
        print("production " + json.loads(active.read_text())["approval_id"])
    except (ValueError, KeyError):
        print("production unreadable")
