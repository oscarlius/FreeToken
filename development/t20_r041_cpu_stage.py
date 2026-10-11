"""Freeze and test the R041 raw-evidence reader on CPU; never admits GPU work."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
CHAIN_PROBE = r'''
import json,pathlib,sys
sys.dont_write_bytecode=True
import d17_gate_case
root=pathlib.Path('/data2/FreeToken/runs/dev_D16/r034a_close_clone_20261005_175316/E2-R034a')
closed=json.loads((root/'round.json').read_text())
assert closed['verdict']=='failed_harness'
review=closed['results']
try:
 d17_gate_case._recompute_closed_t17(root,closed,review)
except d17_gate_case.D17GateError as e:
 assert 'actual T17 audit lacks the exact 28 cases' in str(e),str(e)
 print(json.dumps({'canonical_d04_and_actual_raw_audit':'recomputed_failed_harness','acceptance_rejected':True,'model_admitted':False}))
else:
 raise AssertionError('failed_harness clone must never admit T17')
'''
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=pathlib.Path('/data2/_shared/gpu.lock')
def identity():
 if not lock.exists():return None
 s=lock.stat();return [sha(lock),s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns]
before=identity()
for name,raw in x['files'].items():
 p=stage/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(base64.b64decode(raw))
inputs=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R035/real_inputs.json').read_bytes()
assert hashlib.sha256(inputs).hexdigest()=='90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0'
with (stage/'realinput_28.json').open('xb') as f:f.write(inputs)
env={k:v for k,v in os.environ.items() if not k.startswith('FT_') and k not in ('PYTHONPATH','PYTHONOPTIMIZE')}
env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t20_r041_sample4_closure.py','tests/test_d17_gpu_gate_runner.py','tests/test_d16_service_workloads.py','tests/test_t17_artifacts_bytes.py','tests/test_t17_runtime_r041_recheck.py','tests/test_t17_continuation_selection.py','tests/test_t17_continuation_runner_v2.py']
p=subprocess.run(argv,cwd=stage,env=env,capture_output=True,text=True)
log=stage/'pytest.log';log.write_text(p.stdout+p.stderr)
probe_argv=[sys.executable,str(stage/'chain_probe.py')]
probe=subprocess.run(probe_argv,cwd=stage,env=env,capture_output=True,text=True)
(stage/'chain_probe.log').write_text(probe.stdout+probe.stderr)
report={'schema':'ft_t20_r041_reader_cpu/v1','verdict':'PASS' if p.returncode==0 and probe.returncode==0 else 'FAIL','returncode':p.returncode,'argv':argv,'chain_probe_argv':probe_argv,'chain_probe_returncode':probe.returncode,'positive_accepted_t17_r041_chain_verified':False,'fixture_only':True,'model_admitted':False,'gpu_started':False,'requests_sent':False,'target_model_requests_sent':False,'fixture_http_requests_sent':True,'gpu_lock_unchanged':identity()==before,'files':{q.relative_to(stage).as_posix():sha(q) for q in stage.rglob('*') if q.is_file()}}
assert report['gpu_lock_unchanged']
r=stage/'cpu_validation.json';r.write_text(json.dumps(report,sort_keys=True)+'\n')
for q in sorted(stage.rglob('*'),reverse=True):q.chmod(0o444 if q.is_file() else 0o555)
stage.chmod(0o555)
print(json.dumps({'stage':str(stage),'report_sha256':sha(r),'verdict':report['verdict'],'log':p.stdout+p.stderr,'chain_probe':probe.stdout+probe.stderr}),flush=True)
sys.exit(0 if report['verdict']=='PASS' else 1)
'''


def main():
    names = ('t20_r041_sample4_closure.py', 'd17_gpu_gate_runner.py', 'd17_gate_case.py',
             'd17_source_admission.py', 'd17_frozen_helpers.py', 't17_continuation_runner.py',
             't17_continuation_runtime_v2.py', 'tests/test_t17_runtime_r041_recheck.py',
             'd16_service_workloads.py', 't17_d14_runner.py', 'tests/test_d16_service_workloads.py',
             't17_d14_artifacts.py', 't16_full_tail_base_runner.py', 'tests/test_t17_artifacts_bytes.py',
             'tests/test_t20_r041_sample4_closure.py', 'tests/test_d17_gpu_gate_runner.py')
    files = {name: (HERE / name).read_bytes() for name in names}
    # The accepted-T17 reader loads its independent auditor dynamically.
    for name in ('t17_continuation_review.py', 't17_operator_observe.py',
                 't17_continuation_selection.py', 't17_continuation_runner_v2.py',
                 't17_continuation_inputs_cpu_fd6362813705.json'):
        files[name] = (HERE / name).read_bytes()
    for name in ('test_t17_continuation_selection.py', 'test_t17_continuation_runner_v2.py'):
        files['tests/' + name] = (HERE.parent / 'tests' / name).read_bytes()
    for path in (HERE / 'e2base1/scripts/equiv_suite').glob('*.py'):
        files['equiv_suite/' + path.name] = path.read_bytes()
    files['serve_args_diff.py'] = (HERE.parent / 'scripts/serve_args_diff.py').read_bytes()
    files['round_json_append.py'] = (HERE.parent / 'scripts/round_json_append.py').read_bytes()
    files['stage_source.py'] = Path(__file__).read_bytes()
    files['stage_program.py'] = PROGRAM.encode()
    files['chain_probe.py'] = CHAIN_PROBE.encode()
    key = hashlib.sha256(b''.join(name.encode() + files[name] for name in sorted(files))).hexdigest()[:12]
    payload = {'stage': '/data2/FreeToken/runs/dev_D16/t20_r041_reader_cpu_' + key,
               'files': {name: base64.b64encode(raw).decode() for name, raw in files.items()}}
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(payload)) + ')\n' + PROGRAM
    p = subprocess.run(['ssh', '-o', 'BatchMode=yes', '9', '/data2/FreeToken/venv/bin/python', '-'],
                       input=wire, text=True, capture_output=True)
    with (HERE / ('t20_r041_reader_cpu_' + key + '.json')).open('x', encoding='utf-8') as f:
        json.dump({'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}, f, indent=2)
    print(p.stdout); print(p.stderr)
    raise SystemExit(p.returncode)


if __name__ == '__main__':
    main()
