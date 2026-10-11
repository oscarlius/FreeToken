"""Freeze and CPU-test the independent T17 reader separately from the GPU batch."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,data in x['files'].items():
 p=stage/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(base64.b64decode(data))
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
p=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t17_continuation_review.py'],cwd=stage,env=env,capture_output=True)
with (stage/'regression.log').open('xb') as f:f.write(p.stdout+p.stderr)
report={'schema':'ft_t17_continuation_review_cpu/v1','verdict':'PASS' if p.returncode==0 else 'FAIL',
 'returncode':p.returncode,'gpu_started':False,'requests_sent':False,
 'files':{p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}}
with (stage/'cpu_validation.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
stage.chmod(0o555)
print(json.dumps(dict(stage=str(stage),report_sha256=sha(stage/'cpu_validation.json'),**report)))
'''

def main():
    names = ['t17_continuation_review.py','tests/test_t17_continuation_review.py',
             't17_d14_artifacts.py','t17_operator_observe.py']
    files = {name:(HERE/name).read_bytes() for name in names}
    for source in (HERE/'e2d16-tools/scripts/equiv_suite').glob('*.py'):
        files['e2d16-tools/scripts/equiv_suite/'+source.name]=source.read_bytes()
    files['stage_program.py']=PROGRAM.encode()
    files['stage_source.py']=Path(__file__).read_bytes()
    digest=hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
    payload={'stage':'/data2/FreeToken/runs/dev_D16/continuation_review_cpu_'+digest[:12],
             'files':{name:base64.b64encode(data).decode() for name,data in files.items()}}
    program='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    p=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],
                     input=program.encode(),capture_output=True)
    report={'returncode':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()}
    if p.returncode==0:report.update(json.loads(p.stdout))
    with (HERE/('t17_continuation_review_cpu_'+digest[:12]+'.json')).open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report))
    if p.returncode or report.get('verdict')!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
