"""Freeze and CPU-test the exact R032 auditor; writing its review is explicit."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
FILES = ('t16_r032_review.py', 't16_r022_review.py', 'tests/test_t16_r032_review.py',
         't16_r032_review_stage.py')
PROGRAM = r'''import base64,hashlib,json,os,pathlib,re,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,raw):
 with p.open('xb') as f:f.write(raw)
env={k:v for k,v in os.environ.items() if not k.startswith(('FT_DEV_','FT_T17_','FT_D3_'))}
env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
if x['mode']=='stage':
 stage.mkdir(exist_ok=False);error=None;passed=0;step=None
 try:
  for name,data in x['files'].items():
   path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);write(path,base64.b64decode(data))
  command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t16_r032_review.py']
  run=subprocess.run(command,cwd=stage,env=env,capture_output=True,timeout=180)
  write(stage/'regression.log',run.stdout+run.stderr)
  step={'returncode':run.returncode,'log_sha256':sha(stage/'regression.log')}
  text=(run.stdout+run.stderr).decode();matches=re.findall(r'(\d+) passed',text)
  if run.returncode or matches!=['11'] or re.search(r'\d+ (failed|skipped|error)',text):raise ValueError('complete Linux auditor regression required')
  passed=11
 except BaseException as exc:error=repr(exc)
 finally:
  report={'schema':'ft_t16_r032_review_stage/v1','gpu_started':False,'requests_sent':False,'verdict':'FAIL' if error else 'PASS','passed':passed,'step':step,'files':{name:sha(stage/name) for name in x['files'] if (stage/name).is_file()},'error':error}
  write(stage/'cpu_validation.json',(json.dumps(report,indent=2)+'\n').encode())
  for path in sorted(stage.rglob('*'),reverse=True):path.chmod(0o444 if path.is_file() else 0o555)
  stage.chmod(0o555)
  print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),**report}))
else:
 report=json.loads((stage/'cpu_validation.json').read_bytes())
 if sha(stage/'cpu_validation.json')!=x['report_sha256'] or report['verdict']!='PASS' or report['passed']!=11:raise ValueError('exact successful auditor CPU stage required')
 for name,digest in report['files'].items():
  path=stage/name
  if path.is_symlink() or path.stat().st_mode&0o222 or sha(path)!=digest:raise ValueError('frozen auditor changed: '+name)
 log=stage/'regression.log'
 if log.is_symlink() or log.stat().st_mode&0o222 or sha(log)!=report['step']['log_sha256']:raise ValueError('auditor CPU log changed')
 if stage.is_symlink() or stage.stat().st_mode&0o222 or stage.stat().st_uid!=os.geteuid():raise ValueError('owned readonly auditor stage required')
 run=subprocess.run([sys.executable,str(stage/'t16_r032_review.py'),'--review'],cwd=stage,env=env,capture_output=True,timeout=180)
 if run.returncode:print((run.stdout+run.stderr).decode(),file=sys.stderr);raise SystemExit(run.returncode)
 print(run.stdout.decode())
'''


def remote(payload):
    wire = 'import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    run = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                          '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True)
    if run.returncode: raise RuntimeError((run.stderr+run.stdout).decode())
    return json.loads(run.stdout)


def exclusive(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')


def stage():
    files = {name: (HERE/name).read_bytes() for name in FILES}
    files['stage_program.py'] = PROGRAM.encode()
    identity = hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
    result = remote({'mode': 'stage', 'stage': '/data2/FreeToken/runs/dev_D14/t16_r032_review_'+identity[:12],
                     'files': {name: base64.b64encode(raw).decode() for name, raw in files.items()}})
    exclusive(HERE/('t16_r032_review_stage_'+identity[:12]+'.json'), result)
    if result['verdict'] != 'PASS': raise ValueError('failed auditor CPU stage retained')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, help='exact successful CPU stage receipt')
    args = parser.parse_args()
    if args.review:
        receipt = json.loads(args.review.read_bytes())
        result = remote({'mode': 'review', 'stage': receipt['stage'], 'report_sha256': receipt['report_sha256']})
        exclusive(HERE/'t16_r032_raw_review.json', result)
        print(json.dumps({'rid':result['rid'],'verdict':result['verdict'],'review_sha256':result['review_sha256']}))
    else:
        result = stage()
        print(json.dumps({'stage':result['stage'],'passed':result['passed'],'report_sha256':result['report_sha256']}))
