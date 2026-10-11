"""Freeze and CPU-test the dedicated R032 close controller before any close."""
from __future__ import annotations
import argparse, base64, hashlib, json, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ('t16_r032_close.py', 't16_r032_close_stage.py', 'tests/test_t16_r032_close.py', 'round_json_append.py', 'round_close.py', 'round_close.sh')
PROGRAM = r'''import base64,hashlib,json,os,pathlib,re,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze():
 for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
stage.mkdir(parents=True,exist_ok=False);error=None;step=None;passed=0
try:
 for name,data in x['files'].items():
  p=stage/name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(base64.b64decode(data))
 env={k:v for k,v in os.environ.items() if not k.startswith(('FT_DEV_','FT_T17_','FT_D3_'))};env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
 run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t16_r032_close.py'],cwd=stage,env=env,capture_output=True,timeout=180)
 (stage/'regression.log').write_bytes(run.stdout+run.stderr);step={'returncode':run.returncode,'log_sha256':sha(stage/'regression.log')}
 hits=re.findall(r'(\d+) passed',(run.stdout+run.stderr).decode())
 if run.returncode or hits!=['7'] or re.search(r'\d+ (failed|skipped|error)',(run.stdout+run.stderr).decode()):raise ValueError('complete seven-test close-stage CPU regression required')
 passed=int(hits[-1])
except BaseException as exc:error=repr(exc)
finally:
 report={'schema':'ft_t16_r032_close_stage/v1','gpu_started':False,'requests_sent':False,'verdict':'PASS' if error is None else 'FAIL','passed':passed,'step':step,'files':{n:sha(stage/n) for n in x['files'] if (stage/n).is_file()},'error':error}
 with (stage/'cpu_validation.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 freeze();print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),**report}),flush=True)
'''

OPERATION = r'''import hashlib,importlib.util,json,os,pathlib,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if stage.is_symlink() or not stage.is_dir() or stage.stat().st_mode&0o222 or stage.stat().st_uid!=os.geteuid():raise ValueError('owned immutable close stage required')
report_path=stage/'cpu_validation.json'
if report_path.is_symlink() or report_path.stat().st_mode&0o222 or sha(report_path)!=x['report_sha256']:raise ValueError('exact close CPU report differs')
report=json.loads(report_path.read_bytes())
if report.get('verdict')!='PASS' or report.get('passed')!=7 or report.get('gpu_started') is not False or report.get('requests_sent') is not False or report.get('files')!=x['files']:raise ValueError('exact successful close CPU binding required')
for name,digest in report['files'].items():
 relative=pathlib.Path(name);p=stage/relative
 if relative.is_absolute() or '..' in relative.parts or p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222 or p.stat().st_uid!=os.geteuid() or sha(p)!=digest:raise ValueError('frozen close source changed: '+name)
source=stage/'t16_r032_close.py';spec=importlib.util.spec_from_file_location('r032_frozen_close',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.validate_closure_stage(stage)
result=module.close(execute=x['mode']=='close',closure_stage=stage,audit_receipt=pathlib.Path(x['audit_path']) if x.get('audit_path') else None)
print(json.dumps(result,sort_keys=True,default=str))
'''
def _sha(data): return hashlib.sha256(data).hexdigest()
def exclusive(path, value):
 with path.open('x', encoding='utf-8') as stream: json.dump(value, stream, indent=2); stream.write('\n')
def remote(payload, program=PROGRAM):
 wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+program
 run=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9','/data2/FreeToken/venv/bin/python','-'],input=wire.encode(),capture_output=True)
 if run.returncode: raise RuntimeError((run.stderr+run.stdout).decode())
 return json.loads(run.stdout)
def stage():
 files={name:((HERE.parent/'scripts'/name) if name.startswith('round_') else (HERE/name)).read_bytes() for name in FILES};files['stage_program.py']=PROGRAM.encode()
 identity=_sha(b''.join(name.encode()+files[name] for name in sorted(files)))
 result=remote({'stage':'/data2/FreeToken/runs/dev_D14/t16_r032_close_'+identity[:12],'files':{name:base64.b64encode(data).decode() for name,data in files.items()}})
 exclusive(HERE/('t16_r032_close_stage_'+identity[:12]+'.json'),result)
 if result['verdict']!='PASS': raise ValueError('retained close CPU stage failed')
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--prepare',type=Path);parser.add_argument('--close',type=Path);parser.add_argument('--audit',type=Path);args=parser.parse_args()
 if args.prepare and args.close: parser.error('--prepare and --close are mutually exclusive')
 if not args.prepare and not args.close: result=stage()
 else:
  receipt=json.loads((args.prepare or args.close).read_bytes())
  if args.close and args.audit is None: raise ValueError('--close requires an explicit independent audit receipt')
  result=remote({'mode':'close' if args.close else 'prepare','stage':receipt['stage'],
                 'report_sha256':receipt['report_sha256'],'files':receipt['files'],
                 'audit_path':str(args.audit) if args.audit else None},OPERATION)
  exclusive(HERE/('t16_r032_closure.json' if args.close else 't16_r032_close_preparation.json'),result)
 print(json.dumps(result,sort_keys=True,default=str))
