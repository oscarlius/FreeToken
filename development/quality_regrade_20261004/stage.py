"""Freeze the standard, run Linux regression and grade three historical sets."""
import base64,hashlib,json,shlex,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
files={name:(HERE/name).read_bytes() for name in ('regrade.py','test_regrade.py','evaluator_previous_250e197f.py')}
files.update({'evaluator.py':(ROOT.parent/'_shared/evaluator.py').read_bytes(),
              'test_prompts_60.json':(ROOT.parent/'_shared/test_prompts_60.json').read_bytes()})
identity=hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
stage='/data2/FreeToken/runs/quality_regrade_'+identity[:12]
PROGRAM=r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
payload=json.load(sys.stdin);stage=pathlib.Path(payload['stage']);stage.mkdir(exist_ok=False)
for name,value in payload['files'].items():
 with (stage/name).open('xb') as stream:stream.write(base64.b64decode(value))
env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
try:
 test=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'test_regrade.py')],
                     cwd=stage,capture_output=True,env=env)
 (stage/'tests.log').write_bytes(test.stdout+test.stderr)
 if test.returncode:print((test.stdout+test.stderr).decode(),file=sys.stderr);raise SystemExit(test.returncode)
 report={'schema':'ft_quality_regrade_cpu/v1','gpu_started':False,'returncode':0,
         'test_log_sha256':hashlib.sha256((stage/'tests.log').read_bytes()).hexdigest(),
         'source_files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in payload['files']}}
 (stage/'cpu_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 for path in stage.iterdir():path.chmod(path.stat().st_mode&~0o222)
 stage.chmod(stage.stat().st_mode&~0o222)
 run=subprocess.run([sys.executable,str(stage/'regrade.py')],capture_output=True,env=env)
 if run.returncode:print((run.stdout+run.stderr).decode(),file=sys.stderr);raise SystemExit(run.returncode)
 result=json.loads(run.stdout)
 print(json.dumps({'stage':str(stage),'cpu_receipt_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest(),
                   'tests':test.stdout.decode().strip().splitlines()[-1],
                   'result':result},ensure_ascii=False))
finally:
 for path in [stage,*stage.rglob('*')]:path.chmod(path.stat().st_mode&~0o222)
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                      input=json.dumps({'stage':stage,'files':{name:base64.b64encode(value).decode() for name,value in files.items()}}).encode(),
                      capture_output=True)
if result.returncode:print('Retained stage:',stage);print(result.stderr.decode());raise SystemExit(result.returncode)
receipt=json.loads(result.stdout)
with (HERE/'measure_receipt.json').open('x',encoding='utf-8') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
