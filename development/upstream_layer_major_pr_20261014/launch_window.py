"""Launch only the sealed, explicitly approved one-shot controller."""
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    ops.run(client,r'''
import hashlib, json, os, pathlib, subprocess, time
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
ready=json.loads((root/'WINDOW_CPU_READY.json').read_text())
assert hashlib.sha256((root/'gpu_window_ready.py').read_bytes()).hexdigest()==ready['executor_sha256']
assert hashlib.sha256((root/'WINDOW_AUTHORIZATION_SEALED.json').read_bytes()).hexdigest()==ready['authorization_sha256']
assert not (root/'WINDOW_RUN_CONSUMED.json').exists() and not (root/'WINDOW_LAUNCH.json').exists()
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1')
argv=['/data2/FreeToken/venv/bin/python','-u',str(root/'gpu_window_ready.py'),'--run']
with (root/'window_supervisor.log').open('xb') as f:
    child=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
birth=pathlib.Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()
record={'at':time.time(),'pid':child.pid,'start_ticks':int(birth[19]),'argv':argv,
        'executor_sha256':ready['executor_sha256'],'authorization_sha256':ready['authorization_sha256']}
with (root/'WINDOW_LAUNCH.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record,indent=2))
''')
    sftp=client.open_sftp();sftp.get('/data2/FreeToken/development/upstream_layer_major_pr_20261014/WINDOW_LAUNCH.json',str(HERE/'WINDOW_LAUNCH.json'));sftp.close()
finally:client.close()
