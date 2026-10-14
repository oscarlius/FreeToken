"""Bind isolated native builds and CPU preflight to the contribution candidate."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    sftp = client.open_sftp()
    remote = '/data2/FreeToken/development/upstream_layer_major_pr_20261014/'
    for name in ('native_observer.py', 'test_native_observer.py', 'gpu_client.py', 'test_gpu_client.py'):
        sftp.put(str(HERE/name), remote + name)
    sftp.close()
    ops.run(client, r'''
import datetime, hashlib, json, os, pathlib, subprocess
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
source = root/'candidate_63858fa'
env = dict(os.environ, CUDA_VISIBLE_DEVICES='', CUDA_HOME='/usr/local/cuda-13.0',
           PATH='/usr/local/cuda-13.0/bin:'+os.environ['PATH'], OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           PYTHONPATH=str(source/'python')+':'+str(root))
py = str(root/'main-venv/bin/python')
code = "import torch; from freetoken.kernel import _pinned_tensor, _cpu_moe, _row_store; from freetoken.scheduler.io import SchedulerIOMixin; from freetoken.message import DetokenizeMsg; import native_observer; print(torch.__version__, torch.version.cuda); print('ALL_NATIVE_IMPORTS_PASS')"
checks = []
for argv in ([py,'-c',code], [py,'-m','freetoken.cli','serve','--help'],
             [py,'-m','unittest','-v','test_gpu_client.py','test_native_observer.py']):
    result = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=120)
    checks.append({'argv':argv,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    assert result.returncode == 0, checks[-1]
receipt = {'at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
           'commit':'63858faa584ddd623d5ea1728e26270e0c7f649b',
           'cuda_visible_devices':'', 'native_modules':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (source/'python/freetoken/kernel').glob('*.so')},
           'build_log_sha256':hashlib.sha256((root/'native_build.log').read_bytes()).hexdigest(),
           'checks':checks,'gpu_model_measurement':False,'production_untouched':True}
with (root/'NATIVE_CPU_PREFLIGHT_01.json').open('x') as handle: json.dump(receipt,handle,indent=2)
print(json.dumps({'native_modules':list(receipt['native_modules']),
                  'checks':[{'argv':x['argv'][:3], 'exit_code':x['exit_code']} for x in checks]},indent=2))
''')
    sftp = client.open_sftp()
    for name in ('NATIVE_CPU_PREFLIGHT_01.json', 'native_build.log'):
        sftp.get(remote+name, str(HERE/name))
    sftp.close()
finally:
    client.close()
