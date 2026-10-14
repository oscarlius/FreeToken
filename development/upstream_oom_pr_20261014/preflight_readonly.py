"""Read current host/runtime and reusable isolated test environment without mutation."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
import datetime,json,pathlib,subprocess
facts={'at':datetime.datetime.now().astimezone().isoformat()}
commands={
 'gpu':['nvidia-smi','--query-gpu=index,name,memory.total,memory.used,utilization.gpu','--format=csv,noheader'],
 'compute':['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader'],
 'uptime':['uptime'],
 'ollama':['docker','inspect','--format','{{.State.Running}}','ollama'],
 'processes':['ps','-eo','pid,stat,args'],
}
for name,argv in commands.items():
 result=subprocess.run(argv,capture_output=True,text=True,timeout=15)
 output=result.stdout
 if name=='processes':
  output='\n'.join(line[:360] for line in output.splitlines() if any(x in line for x in ('freetoken','aiperf','gpu_window','benchmark','nvcc','ninja')) and 'python -c' not in line)
 facts[name]={'returncode':result.returncode,'stdout':output}
active=pathlib.Path('/data2/FreeToken/run/production.active.json')
if active.exists():
 value=json.loads(active.read_text())
 facts['active']={key:value.get(key) for key in ('approval_id','commit','run_dir','pid','start_ticks','service_pid','supervisor_pid','argv')}
venv=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv/bin/python')
facts['test_python_exists']=venv.is_file()
print(json.dumps(facts,indent=2,ensure_ascii=False))
''')
finally:
    client.close()
