"""Freeze T17 sources and prove actual spawned startup and history IDs on CPU."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
NAMES = ('t17_d14_runner.py', 't17_d14_gpu.py', 't17_d14_launch.py',
         't17_owned_launch_protocol.py', 't16_full_tail_base_runner.py',
         't17_d14_observe.py', 't17_d14_artifacts.py', 'test_t17_d14_runner.py',
         'test_t17_d14_artifacts.py', 'tests/test_t17_d14_gpu.py')
files = {name: (HERE/name).read_bytes() for name in NAMES}
files['stage_source.py'] = Path(__file__).read_bytes()
identity = hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
stage = '/data2/FreeToken/runs/dev_D14/t17_' + identity[:12]
payload = {'stage': stage, 'files': {name: base64.b64encode(data).decode() for name, data in files.items()}}
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(parents=True,exist_ok=False)
for name,encoded in data['files'].items():
 relative=pathlib.PurePosixPath(name)
 assert not relative.is_absolute() and '..' not in relative.parts
 path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as stream:stream.write(base64.b64decode(encoded))
tree=pathlib.Path('/data2/FreeToken/wt/e2d14');py='/data2/FreeToken/venv/bin/python'
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONPATH=str(tree/'python')+':'+str(tree),FT_DEV_STATE_DUMP=str(stage/'cpu_unused_dump'),FT_T17_OBSERVATIONS=str(stage/'cpu_observations.jsonl'))
for key in list(env):
 if (key.startswith(('FT_T17_','FT_D3_')) and key!='FT_T17_OBSERVATIONS') or key.startswith('FT_DEV_') and key!='FT_DEV_STATE_DUMP':env.pop(key)
def run(name,args,timeout=180):
 process=subprocess.run(args,cwd=stage,env=env,capture_output=True,timeout=timeout)
 path=stage/(name+'.log');path.write_bytes(process.stdout+process.stderr)
 if process.returncode:
  print((process.stdout+process.stderr).decode(errors='replace')[-8000:],file=sys.stderr)
  raise SystemExit(process.returncode)
 return {'returncode':0,'log_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'stdout':process.stdout.decode()}
try:
 tests=run('helper_tests',[py,str(stage/'test_t17_d14_runner.py')])
 gpu_tests=run('gate_tests',[py,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'tests/test_t17_d14_gpu.py')])
 raw_tests=run('raw_tests',[py,str(stage/'test_t17_d14_artifacts.py')])
 assert 'Ran 14 tests' in (stage/'helper_tests.log').read_text() and '10 passed' in gpu_tests['stdout'] and 'Ran 3 tests' in (stage/'raw_tests.log').read_text()
 run('freeze_wrapper',[py,'-c','import pathlib,t17_d14_runner as h; h.freeze_startup_wrapper(pathlib.Path.cwd())'])
 bits=run('byte_comparison',[py,'-c',"import torch,t17_d14_artifacts as a; p=torch.tensor([0.]); n=torch.tensor([-0.]); assert torch.equal(p,n) and not a.bit_equal(p,n) and a.bit_equal(p,p); assert not torch.cuda.is_initialized(); print('BYTE_COMPARE_CPU_PASS')"])
 spawn=run('startup_spawn',[py,str(stage/'t17_d14_startup.py'),'--cpu-startup-probe'])
 proof=json.loads(spawn['stdout'].splitlines()[-1]);assert proof['gpu_started'] is False and proof['worker']['cuda_initialized'] is False
 inputs_step=run('build_inputs',[py,str(stage/'t17_d14_gpu.py'),'--build-inputs',str(stage/'real_inputs.json')],300)
 inputs=json.loads((stage/'real_inputs.json').read_text());assert len(inputs['cases'])==4
 names=tuple(data['files'])+('t17_d14_startup.py','t17_d14_exact_ids.py','real_inputs.json')
 report={'schema':'ft_t17_d14_cpu_stage/v1','gpu_started':False,'source_files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in names},'helper_tests':tests,'gate_tests':gpu_tests,'raw_tests':raw_tests,'byte_comparison':bits,'startup_spawn':spawn,'spawn_proof':proof,'build_inputs':inputs_step,'candidate_commit':inputs['candidate_commit'],'case_lengths':[case['length'] for case in inputs['cases']]}
 (stage/'cpu_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'stage':str(stage),'report':report,'report_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest()}))
finally:
 for path in reversed([stage,*sorted(stage.rglob('*'))]):
  assert not path.is_symlink();path.chmod(path.stat().st_mode & ~0o222)
'''
result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
                         '/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                        input=json.dumps(payload).encode(), capture_output=True)
if result.returncode:
    print('Retained failed CPU stage:',stage)
    print(result.stderr.decode(errors='replace'))
    raise SystemExit(result.returncode)
receipt=json.loads(result.stdout)
target=HERE/'t17_d14_cpu_receipt.json'
if target.exists():
    previous=target.read_bytes();archive=target.with_name(target.stem+'_'+hashlib.sha256(previous).hexdigest()[:12]+'.json')
    if archive.exists():
        assert archive.read_bytes()==previous
    else:
        with archive.open('xb') as stream:stream.write(previous)
target.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'stage':stage,'report_sha256':receipt['report_sha256'],
                  'case_lengths':receipt['report']['case_lengths'],'spawn_proof':receipt['report']['spawn_proof']},indent=2))
