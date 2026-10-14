"""Read-only bounded snapshot of the authorized OOM validation window."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ops", root.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
import datetime,json,pathlib
root=pathlib.Path('/data2/FreeToken/development/upstream_oom_pr_20261014')
print(datetime.datetime.now().astimezone().isoformat())
for name in ('GPU_WINDOW_TERMINAL.json','window.log','stop_e3.log','restore_start.log','restore_smoke.log'):
 path=root/name
 if path.is_file():print(name+'\n'+path.read_text(errors='replace')[-4500:])
for arm in ('main','candidate_off','candidate_on'):
 base=root/'gpu_results'/arm
 if base.is_dir():
  print('ARM '+arm)
  for name in ('serve.log','client.log','SUMMARY.json'):
   path=base/name
   if path.is_file():
    if name=='SUMMARY.json':print(name+'\n'+json.dumps({k:v for k,v in json.loads(path.read_text()).items() if k!='refs'}))
    else:print(name+'\n'+path.read_text(errors='replace')[-1600:])
active=pathlib.Path('/data2/FreeToken/run/production.active.json')
print('active='+str(json.loads(active.read_text()).get('approval_id')) if active.is_file() else 'active=absent')
if active.is_file():
 run=pathlib.Path(json.loads(active.read_text())['run_dir'])
 for name in ('serve.log','smoke_execution_result.json'):
  path=run/name
  if path.is_file():print('production '+name+'\n'+path.read_text(errors='replace')[-1800:])
''')
finally:
    client.close()
