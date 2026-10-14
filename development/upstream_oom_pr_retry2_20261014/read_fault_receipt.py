"""Read-only fault wire receipt; no generation or control requests."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ops", root.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
from pathlib import Path
root=Path('/data2/FreeToken/development/upstream_oom_pr_retry2_20261014/gpu_results/candidate_on')
for name in ('fault_uid1.sse','native/backend_handles.jsonl','native/oom_faults.jsonl'):
 path=root/name
 if path.is_file():print(name+'\n'+path.read_text()[-1500:])
''')
finally:
    client.close()
