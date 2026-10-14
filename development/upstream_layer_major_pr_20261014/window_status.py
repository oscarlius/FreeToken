"""Read only the bounded controller/service logs; no requests or measurements."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    ops.run(client,r'''
import json, pathlib
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
for name in ('window_supervisor.log','GPU_WINDOW_RECOVERY.json','restore_smoke.log'):
    p=root/name
    if p.exists():print(name,p.read_text(errors='replace')[-1800:])
for arm in ('main','candidate_off','candidate_on'):
    p=root/'gpu_results'/arm
    if not p.exists():continue
    print('arm',arm)
    if not (p/'arm.jsonl').exists():
        for name in ('serve.log','client.log'):
            f=p/name
            if f.exists():print(name,f.read_text(errors='replace')[-1000:])
    r=p/'receipts.jsonl'
    if r.exists():print('receipts',len(r.read_text().splitlines()))
active=pathlib.Path('/data2/FreeToken/run/production.active.json')
print('active_production',json.loads(active.read_text())['approval_id'] if active.exists() else None)
if active.exists():
    run=pathlib.Path(json.loads(active.read_text())['run_dir'])
    for name in ('serve.log','smoke_execution_result.json'):
        f=run/name
        if f.exists():print('production_'+name,f.read_text(errors='replace')[-1200:])
''')
finally:client.close()
