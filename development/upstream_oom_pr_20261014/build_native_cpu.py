"""Build current-base native modules in an owned stage with CUDA hidden."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
import datetime,hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/development/upstream_oom_pr_20261014')
source=root/'baseline_f02fbb1'
venv=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv')
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',CUDA_HOME='/usr/local/cuda-13.0',TORCH_CUDA_ARCH_LIST='8.9',MAX_JOBS='2',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(source/'python'),PYTHONDONTWRITEBYTECODE='1')
env['PATH']=str(venv/'bin')+':/usr/local/cuda-13.0/bin:'+env['PATH']
argv=['nice','-n','19','ionice','-c','3','taskset','-c','0,2',str(venv/'bin/python'),'setup.py','build_ext','--inplace']
started=datetime.datetime.now().astimezone().isoformat()
with (root/'native_build.log').open('xb') as handle:
 result=subprocess.run(argv,cwd=source,env=env,stdout=handle,stderr=subprocess.STDOUT,timeout=1200)
receipt={'at':started,'finished_at':datetime.datetime.now().astimezone().isoformat(),'base':'f02fbb16a213f5c81094e4017c988d41f0164141','exit_code':result.returncode,'argv':argv,'cuda_visible_devices':'','log_sha256':hashlib.sha256((root/'native_build.log').read_bytes()).hexdigest(),'native':{p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'python/freetoken/kernel').glob('*.so')}}
if result.returncode==0:
 check=subprocess.run([str(venv/'bin/python'),'-c','import freetoken.kernel._pinned_tensor, freetoken.kernel._row_store, freetoken.kernel._cpu_moe; print("native imports passed")'],env=env,cwd=source,capture_output=True,text=True,timeout=60)
 receipt['imports']={'exit_code':check.returncode,'stdout':check.stdout,'stderr':check.stderr}
with (root/'NATIVE_BUILD.json').open('x') as handle:json.dump(receipt,handle,indent=2)
print(json.dumps(receipt,indent=2))
if result.returncode:print((root/'native_build.log').read_text()[-5000:])
''')
    sftp = client.open_sftp()
    for name in ("native_build.log", "NATIVE_BUILD.json"):
        sftp.get("/data2/FreeToken/development/upstream_oom_pr_20261014/" + name, str(HERE / name))
    sftp.close()
finally:
    client.close()
