"""Freeze the complete continuation toolchain and validate it on Linux without GPU."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
SOURCES = (
    't17_continuation_runner.py', 't17_d14_runner.py', 't17_d14_gpu.py',
    't17_d14_artifacts.py', 't17_d14_observe.py', 't16_full_tail_base_runner.py',
    't17_operator_observe.py', 't17_operator_startup.py',
    't17_continuation_launch.py', 't17_owned_launch_protocol.py',
    'tests/test_t17_continuation_runner.py', 'tests/test_t17_operator_observe.py',
    'tests/test_t17_operator_startup.py',
    'tests/test_t17_continuation_launch.py', 'tests/test_t17_d14_gpu.py',
)

PROGRAM = r'''
import base64,hashlib,json,os,pathlib,re,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data)
report={'schema':'ft_t17_continuation_cpu/v1','gpu_started':False,'requests_sent':False,'steps':{}}
try:
 for name,encoded in x['files'].items():write(stage/name,base64.b64decode(encoded))
 tree=pathlib.Path('/data2/FreeToken/wt/e2d14-schedule')
 env={k:v for k,v in os.environ.items() if not k.startswith(('FT_DEV_','FT_T17_','FT_D3_'))}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONPATH=str(stage)+':'+str(tree/'python'),PATH='/usr/local/cuda-13.0/bin:'+os.environ.get('PATH',''),LD_LIBRARY_PATH='/usr/local/cuda-13.0/lib64:'+os.environ.get('LD_LIBRARY_PATH',''))
 def run(name,args,timeout=240):
  p=subprocess.run([sys.executable,*args],cwd=stage,env=env,capture_output=True,timeout=timeout)
  write(stage/(name+'.log'),p.stdout+p.stderr)
  report['steps'][name]={'returncode':p.returncode,'log_sha256':sha(stage/(name+'.log'))}
  if p.returncode:raise ValueError(name+' failed: '+(p.stdout+p.stderr).decode(errors='replace')[-2500:])
  return p.stdout.decode()
 tests=run('regression',['-m','pytest','-q','-p','no:cacheprovider',*x['tests']])
 count=re.findall(r'(\d+) passed',tests)
 if len(count)!=1 or re.search(r'\d+ (failed|skipped|error)',tests):raise ValueError('complete regression run required')
 report['passed']=int(count[0])
 syntax=subprocess.run(['bash','-n',str(stage/'batchNN_T17.sh')],capture_output=True)
 write(stage/'batch_syntax.log',syntax.stdout+syntax.stderr)
 report['steps']['batch_syntax']={'returncode':syntax.returncode,'log_sha256':sha(stage/'batch_syntax.log')}
 if syntax.returncode:raise ValueError('original batch shell syntax differs')
 run('historical_replay',['-c',"import json,hashlib;from pathlib import Path;from equiv_suite.historical import replay_t16,replay_r023;root=Path('/data2/_shared/runs/ft_rounds');fixture=Path('tests/fixtures/t16_failed_full_tail.json');data=json.loads(fixture.read_bytes());checks=[];\nfor rid,record in data.items():\n for arm,sources in record['sources'].items():\n  for name,digest in sources.items():\n   path=root/rid/arm/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==digest;checks.append(str(path))\nr=root/'E2-R023-gate-T17/review_batch51.json';digest=hashlib.sha256(r.read_bytes()).hexdigest();assert digest=='86bebc276f56c47299dfd7e5da0385f1c4c9bb0166381c80c917d5c5551d5384';result={'t16':replay_t16(fixture,Path('t16_full_tail_base_runner.py')),'r023':replay_r023(json.loads(r.read_bytes()),review_sha256=digest),'actual_raw_files_verified':checks};Path('historical_replay.json').write_text(json.dumps(result,indent=2)+'\\n');assert result['r023']['verdict']=='indeterminate' and result['r023']['admitted'] is False;print(json.dumps(result))"])
 run('actual_operator_self',['-c',"import json,hashlib;from pathlib import Path;from t17_operator_observe import compare;p=Path('/data2/_shared/runs/ft_rounds/E2-R034/prefix_8192_tail_65_warm/operators');r=p/'op_1_receipt.json';assert hashlib.sha256(r.read_bytes()).hexdigest()=='36907e4ede2971849768d8ee1b27bc43eb61e9a3eebb836404427d8e9a345491';v=compare(p,p);assert v['equal'] is True and v['first_layer_operator_difference'] is None;print(json.dumps(v))"])
 run('freeze_startup',['-c','from pathlib import Path;import t17_d14_runner as h;h.freeze_startup_wrapper(Path.cwd())'])
 env.update(FT_DEV_STATE_DUMP=str(stage/'cpu_unused_dump'),FT_T17_OBSERVATIONS=str(stage/'cpu_observations.jsonl'))
 original=json.loads(run('base_spawn',['t17_d14_startup.py','--cpu-startup-probe']).splitlines()[-1])
 if original.get('gpu_started') is not False or original['worker']['cuda_initialized'] is not False:raise ValueError('actual spawned base instrumentation proof required')
 report['spawn_proof']=original
 env.update(FT_T17_OPERATOR=str(stage/'cpu_unused_operators'),FT_T17_OPERATOR_QUERY_SHA='a'*64,FT_T17_OPERATOR_QUERY_TOKENS='8257',FT_T17_OPERATOR_BOUNDARY='8192')
 operator=json.loads(run('operator_spawn',['t17_operator_startup.py','--cpu-startup-probe']).splitlines()[-1])
 if operator.get('gpu_started') is not False or operator['worker']['cuda_initialized'] is not False:raise ValueError('actual spawned operator instrumentation proof required')
 report['operator_spawn_proof']=operator
 args=['t17_continuation_runner.py','--rid','E2-R033','--batch','1','--inputs','/data2/FreeToken/runs/dev_D16/inputs_cpu_fd6362813705/real_inputs.json','--closure-binding','/data2/FreeToken/runs/dev_D14/r032_closure_binding_20261005.json','--directory','/data2/_shared/runs/ft_rounds/E2-R033']
 preflight=json.loads(run('preflight',args).splitlines()[-1])
 if preflight.get('gpu_started') is not False or preflight.get('cases')!=28:raise ValueError('exact full-matrix CPU preflight required')
 report.update(verdict='PASS',preflight=preflight)
except BaseException as e:report.update(verdict='FAIL',error=repr(e))
finally:
 report['files']={p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}
 write(stage/'cpu_validation.json',(json.dumps(report,indent=2)+'\n').encode())
 for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),**report}))
'''

def main():
    files={name:(HERE/name).read_bytes() for name in SOURCES}
    for path in (HERE.parent/'scripts/equiv_suite').glob('*'):
        if path.is_file():files['equiv_suite/'+path.name]=path.read_bytes()
    files['batchNN_T17.sh']=(HERE.parent/'plan/01_测试与调研/batches/batchNN_T17.sh').read_bytes().replace(b'\r\n',b'\n')
    files['tests/fixtures/t16_failed_full_tail.json']=(HERE/'tests/fixtures/t16_failed_full_tail.json').read_bytes()
    files['stage_source.py']=Path(__file__).read_bytes()
    files['stage_program.py']=PROGRAM.encode()
    identity=hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
    payload={'stage':'/data2/FreeToken/runs/dev_D16/continuation_cpu_'+identity[:12],
             'tests':[name for name in SOURCES if name.startswith('tests/')],
             'files':{name:base64.b64encode(data).decode() for name,data in files.items()}}
    program='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    p=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
                      '/data2/FreeToken/venv/bin/python','-'],input=program.encode(),capture_output=True)
    report={'returncode':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()}
    if not p.returncode:report.update(json.loads(p.stdout))
    receipt=HERE/('t17_continuation_cpu_'+identity[:12]+'.json')
    with receipt.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({'receipt':str(receipt),'stage':payload['stage'],'verdict':report.get('verdict'),'error':report.get('error'),'passed':report.get('passed')}))
    if p.returncode or report.get('verdict')!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
