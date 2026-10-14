"""Append actual-time task milestones locally and to the FreeToken coordination log."""
import datetime
import importlib.util
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
event, detail = sys.argv[1:]
stamp = datetime.datetime.now().astimezone().isoformat()
line = "\n| " + stamp + " | Codex | UPSTREAM_OOM_PR_" + event + " | " + detail.replace("|", "/").replace("\n", " ") + " |\n"
with (root / "milestones.jsonl").open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"at": stamp, "event": event, "detail": detail}, ensure_ascii=False) + "\n")
with (root.parents[1] / "plan/COORDINATION_LOG.md").open("a", encoding="utf-8") as handle:
    handle.write(line)
spec = importlib.util.spec_from_file_location("ops", root.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, "from pathlib import Path\nwith Path('/data2/FreeToken/plan/COORDINATION_LOG.md').open('a') as h:h.write(" + repr(line) + ")\nprint('logged')")
finally:
    client.close()
