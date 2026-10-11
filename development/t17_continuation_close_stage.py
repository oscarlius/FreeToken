"""Freeze the T17 closer, independent auditor, and exact D04 tools; CPU only."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent

PROGRAM=r'''
import base64,hashlib,json,os,pathlib,subprocess,sys,re
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data)
for name,data in x['files'].items():write(stage/name,base64.b64decode(data))
sys.path.insert(0,str(stage));import t17_continuation_close as closer
for name,digest in closer.TOOLS.items():
 p=pathlib.Path('/data2/FreeToken/scripts')/name
 if p.is_symlink() or sha(p)!=digest:raise ValueError('D04 source differs')
 write(stage/'d04_tools'/name,p.read_bytes())
audit=pathlib.Path(x['audit_path'])
if audit.is_symlink() or sha(audit)!=x['audit_sha256'] or audit.stat().st_mode&0o222:raise ValueError('independent audit differs')
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
p=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t17_continuation_close.py','tests/test_t17_continuation_review.py'],cwd=stage,env=env,capture_output=True)
write(stage/'regression.log',p.stdout+p.stderr)
passed=re.findall(r'(\d+) passed',p.stdout.decode())
report={'schema':closer.STAGE_SCHEMA,'verdict':'PASS' if p.returncode==0 and len(passed)==1 else 'FAIL',
 'passed':int(passed[0]) if len(passed)==1 else None,'gpu_started':False,'requests_sent':False,
 'step':{'returncode':p.returncode,'log_sha256':sha(stage/'regression.log')},
 'audit_sha256':x['audit_sha256'],'d04_tools':closer.TOOLS,
 'files':{p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}}
write(stage/'cpu_validation.json',(json.dumps(report,indent=2)+'\n').encode())
for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
stage.chmod(0o555)
print(json.dumps(dict(stage=str(stage),report_sha256=sha(stage/'cpu_validation.json'),**report)))
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-path',required=True)
    parser.add_argument('--audit-sha256',required=True)
    args=parser.parse_args()
    if len(args.audit_sha256)!=64 or any(c not in '0123456789abcdef' for c in args.audit_sha256):
        parser.error('audit SHA256 must be lowercase hex')
    names=('t17_continuation_close.py','t17_continuation_review.py',
           'tests/test_t17_continuation_close.py','tests/test_t17_continuation_review.py',
           't17_d14_artifacts.py','t17_operator_observe.py')
    files={name:(HERE/name).read_bytes() for name in names}
    for p in (HERE/'e2d16-tools/scripts/equiv_suite').glob('*.py'):
        files['e2d16-tools/scripts/equiv_suite/'+p.name]=p.read_bytes()
    files['stage_source.py']=Path(__file__).read_bytes()
    files['stage_program.py']=PROGRAM.encode()
    digest=hashlib.sha256(args.audit_path.encode()+args.audit_sha256.encode()+b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
    payload={'stage':'/data2/FreeToken/runs/dev_D16/continuation_close_cpu_'+digest[:12],
             'audit_sha256':args.audit_sha256,'audit_path':args.audit_path,'files':{name:base64.b64encode(data).decode() for name,data in files.items()}}
    program='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    p=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],
                     input=program.encode(),capture_output=True)
    report={'returncode':p.returncode,'stdout':p.stdout.decode(),'stderr':p.stderr.decode()}
    if not p.returncode:report.update(json.loads(p.stdout))
    with (HERE/('t17_continuation_close_cpu_'+digest[:12]+'.json')).open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:report.get(k) for k in ('stage','verdict','report_sha256','passed','stderr')}))
    if p.returncode or report.get('verdict')!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
