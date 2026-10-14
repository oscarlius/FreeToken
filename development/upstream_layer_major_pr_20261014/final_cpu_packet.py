"""Seal final CPU harness evidence; never starts or stops a model service."""
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
    remote = '/data2/FreeToken/development/upstream_layer_major_pr_20261014/'
    names = ('gpu_client.py', 'test_gpu_client.py', 'native_observer.py', 'test_native_observer.py',
             'spawn_observer_check.py', 'recovery_guard.py', 'observer/sitecustomize.py')
    sftp = client.open_sftp()
    try:
        sftp.mkdir(remote+'observer')
    except OSError:
        pass
    for name in names:
        sftp.put(str(HERE/name), remote+name)
    sftp.close()
    ops.run(client, r'''
import datetime, hashlib, json, os, pathlib, subprocess, sys
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
source = root/'candidate_63858fa'
env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           PYTHONPATH=str(root/'observer')+':'+str(root)+':'+str(source/'python'),
           FT_UPSTREAM_NATIVE_IDS=str(root/'spawn_cpu_native_ids_01'))
assert not (root/'spawn_cpu_native_ids_01').exists()
checks = []
py = str(root/'main-venv/bin/python')
for argv in ([py,'-m','unittest','-v','test_gpu_client.py','test_native_observer.py'],
             [py,str(root/'spawn_observer_check.py')]):
    result = subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=120)
    checks.append({'argv':argv,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    assert result.returncode == 0, checks[-1]
sys.path.insert(0,str(root))
import recovery_guard
prod = pathlib.Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-02')
approval = json.loads((prod/'deployment_approval.json').read_text())
integrity = recovery_guard.verify_sources(approval)
owner = json.loads((prod/'owner.json').read_text())
active = json.loads(pathlib.Path('/data2/FreeToken/run/production.active.json').read_text())
recovery_guard.verify_active(owner,active)
at = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
receipt = {'at':at,'commit':'63858faa584ddd623d5ea1728e26270e0c7f649b',
           'checks':checks,'frozen_recovery_integrity':integrity,
           'active_owner_matches_snapshot':True,'active_approval_id':active['approval_id'],
           'files':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
             ('gpu_client.py','test_gpu_client.py','native_observer.py','test_native_observer.py',
              'spawn_observer_check.py','recovery_guard.py','observer/sitecustomize.py','inputs.json')},
           'gpu_calls':0,'service_actions':0,'push':False,
           'remaining_gate':'new GPU pressure window awareness; fresh recovery identity and live ownership recheck before stop'}
with (root/'FINAL_CPU_PACKET_01.json').open('x') as handle: json.dump(receipt,handle,indent=2)
line = '\n| '+at+' | Codex | UPSTREAM_LM_PR_CPU_READY | candidate63858fa; main-env50CPU tests; 3native modules; native observer actual spawn CPU proof; final harness12tests; noGPU/stop/push/PR; pressure-window awareness pending. |\n'
with pathlib.Path('/data2/FreeToken/plan/COORDINATION_LOG.md').open('a') as handle:handle.write(line)
print(json.dumps({'at':at,'checks':[x['exit_code'] for x in checks],
                  'recovery_integrity':integrity,'production_owner':active['approval_id'],
                  'gpu_calls':0,'service_actions':0},indent=2))
''')
    sftp = client.open_sftp()
    sftp.get(remote+'FINAL_CPU_PACKET_01.json', str(HERE/'FINAL_CPU_PACKET_01.json'))
    sftp.close()
finally:
    client.close()
