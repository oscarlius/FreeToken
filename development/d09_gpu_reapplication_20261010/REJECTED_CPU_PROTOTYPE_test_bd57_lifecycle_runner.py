import json,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent

def run(*args,check=True):return subprocess.run([sys.executable,str(HERE/'bd57_lifecycle_runner.py'),*args],text=True,capture_output=True,check=check)
def test_t16_actual_effects_materialize_eight_default_off_services():
 r=run('--filedry','--stage','t16');d=json.loads(r.stdout)
 assert d['status']=='cpu_filedry_complete' and len(d['bindings'])==8
 assert d['plan']['calls']==100 and d['plan']['flags']==[] and d['plan']['server_args']['message_boundary_ckpt'] is False
 assert all('--enable-message-boundary-ckpt' not in x['argv'] for x in d['bindings'])
 assert d['plan']['input_binding']['sha256'] and sum(13 if i < 4 else 12 for i in range(8))==100
 assert d['effects'].startswith('same Runner/Effects')
def test_t17_blocks_without_new_t16_closure():
 r=run('--filedry','--stage','t17');d=json.loads(r.stdout)
 assert d['status']=='pre_gpu_failed' and 'fresh sealed bd57 T16' in d['reason']
def test_bad_admission_never_reaches_spawn_and_idle_expiry_is_failed_harness():
 with tempfile.TemporaryDirectory() as temp:
  admission=Path(temp)/'admission.json';admission.write_text(json.dumps({'root_approved':False,'candidate':'bd57cfdccc2a935d46cb0a89b8b36be7a18706de','stage':'t16'}))
  r=run('--run','--stage','t16','--admission',str(admission),check=False)
  assert r.returncode and 'root admission rejects execution' in r.stderr
 import importlib.util
 spec=importlib.util.spec_from_file_location('runner',HERE/'bd57_lifecycle_runner.py');runner=importlib.util.module_from_spec(spec);sys.modules[spec.name]=runner;spec.loader.exec_module(runner)
 e=runner.Effects(Path(tempfile.mkdtemp()),idle_callback=lambda:False)
 try:e.wait_gpu_idle(runner.time.monotonic())
 except RuntimeError as err:assert 'failed_harness GPU idle wait expired' in str(err)
 else:raise AssertionError('busy driver must fail closed')
