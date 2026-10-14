"""Read GPU/process identities to diagnose post-exit cleanup without sending signals."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    ops.run(client,r'''
import json, pathlib, subprocess, time
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
pids=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],text=True)
print('GPU compute',pids)
print('GPU memory',subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True))
for row in pids.splitlines():
    pid=row.split(',')[0].strip()
    p=pathlib.Path('/proc')/pid
    if p.exists():
        st=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
        argv=p.joinpath('cmdline').read_bytes().split(b'\0')
        print(json.dumps({'pid':pid,'state':st[0],'ppid':st[1],'pgid':st[2],'session':st[3],
                          'start_ticks':st[19],'executable':argv[0].decode(errors='replace')}))
print('lock',pathlib.Path('/data2/_shared/gpu.lock').exists())
print('active',pathlib.Path('/data2/FreeToken/run/production.active.json').exists())
''')
finally:client.close()
