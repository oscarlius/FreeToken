"""Freeze and execute actual target-frontend input construction without a GPU."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
FILES=('t17_continuation_inputs.py','tests/test_t17_continuation_inputs.py',
       't17_continuation_inputs_stage.py','t17_d14_gpu.py','t17_d14_runner.py',
       't17_d14_artifacts.py','t16_full_tail_base_runner.py')
PROGRAM=r'''import base64,hashlib,json,os,pathlib,re,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,raw):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(raw)
report={'schema':'ft_t17_continuation_inputs_cpu/v1','gpu_started':False,'requests_sent':False,'steps':{}}
try:
 for name,data in x['files'].items():write(stage/name,base64.b64decode(data))
 tree=pathlib.Path('/data2/FreeToken/wt/e2d14-schedule')
 if subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()!=x['candidate_commit'] or subprocess.check_output(['git','-C',str(tree),'status','--porcelain','--untracked-files=no'],text=True).strip():raise ValueError('exact clean D14 target candidate required')
 env={k:v for k,v in os.environ.items() if not k.startswith(('FT_DEV_','FT_T17_','FT_D3_'))}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONPATH=str(stage)+':'+str(tree/'python'),PATH='/usr/local/cuda-13.0/bin:'+os.environ.get('PATH',''),LD_LIBRARY_PATH='/usr/local/cuda-13.0/lib64:'+os.environ.get('LD_LIBRARY_PATH',''))
 run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t17_continuation_inputs.py'],cwd=stage,env=env,capture_output=True,timeout=180)
 write(stage/'regression.log',run.stdout+run.stderr)
 output=(run.stdout+run.stderr).decode()
 report['steps']['tests']={'returncode':run.returncode,'log_sha256':sha(stage/'regression.log')}
 if run.returncode or re.findall(r'(\d+) passed',output)!=['5'] or re.search(r'\d+ (failed|skipped|error)',output):raise ValueError('complete five-test input matrix regression required')
 run=subprocess.run([sys.executable,str(stage/'t17_continuation_inputs.py')],cwd=stage,env=env,capture_output=True,timeout=240)
 write(stage/'build.stderr.log',run.stderr);write(stage/'build.stdout.json',run.stdout)
 report['steps']['builder']={'returncode':run.returncode,'stdout_sha256':sha(stage/'build.stdout.json'),'stderr_sha256':sha(stage/'build.stderr.log')}
 if run.returncode:raise ValueError('actual target frontend CPU construction failed')
 inputs=json.loads(run.stdout)
 if inputs.get('gpu_started') is not False or inputs.get('requests_sent') is not False or inputs.get('candidate_commit')!=x['candidate_commit'] or len(inputs.get('cases',[]))!=28:raise ValueError('target frontend matrix receipt differs')
 write(stage/'real_inputs.json',(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n').encode())
 report.update(verdict='PASS',passed=5,candidate_commit=x['candidate_commit'],inputs_sha256=sha(stage/'real_inputs.json'),cases=[{k:r[k] for k in ('name','length','tail','trace_index','expected_ngram','input_ids_sha256','donor_input_ids_sha256')} for r in inputs['cases']],trace_sha256=inputs['trace_sha256'])
except BaseException as error:report.update(verdict='FAIL',error=repr(error))
finally:
 report['files']={p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}
 write(stage/'cpu_validation.json',(json.dumps(report,indent=2)+'\n').encode())
 for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),**report}))
'''


def main():
    files={name:(HERE/name).read_bytes() for name in FILES}
    files['stage_program.py']=PROGRAM.encode()
    identity=hashlib.sha256(b''.join(k.encode()+files[k] for k in sorted(files))).hexdigest()
    payload={'stage':'/data2/FreeToken/runs/dev_D16/inputs_cpu_'+identity[:12],
             'candidate_commit':'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7',
             'files':{k:base64.b64encode(v).decode() for k,v in files.items()}}
    wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    run=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9','/data2/FreeToken/venv/bin/python','-'],input=wire.encode(),capture_output=True)
    result={'returncode':run.returncode,'stdout':run.stdout.decode(),'stderr':run.stderr.decode()}
    if not run.returncode:result.update(json.loads(run.stdout))
    receipt=HERE/('t17_continuation_inputs_cpu_'+identity[:12]+'.json')
    with receipt.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    if run.returncode or result['verdict']!='PASS':raise ValueError('failed input CPU stage retained: '+str(receipt))
    print(json.dumps({'stage':result['stage'],'receipt':str(receipt),'report_sha256':result['report_sha256'],'cases':len(result['cases'])}))


if __name__=='__main__':main()
