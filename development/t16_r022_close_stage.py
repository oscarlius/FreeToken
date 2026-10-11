"""Freeze the reviewed R022 auditor/closer and execute D04 exact-scope closure."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
files={name:(HERE/name).read_bytes() for name in ('t16_r022_review.py','t16_r022_close.py')}
files.update({name:(HERE.parent/'scripts'/name).read_bytes() for name in ('round_json_append.py','round_close.py','round_close.sh')})
identity=hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
stage='/data2/FreeToken/runs/dev_D14/r022_close_'+identity[:12]
payload={'stage':stage,'files':{name:base64.b64encode(data).decode() for name,data in files.items()}}
PROGRAM=r'''
import base64,json,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(exist_ok=False)
for name,value in data['files'].items():
 with (stage/name).open('xb') as stream:stream.write(base64.b64decode(value))
try:
 for name,args in [('audit',['t16_r022_review.py','--review']),('close',['t16_r022_close.py'])]:
  process=subprocess.run([sys.executable,str(stage/args[0]),*args[1:]],capture_output=True)
  (stage/(name+'.log')).write_bytes(process.stdout+process.stderr)
  if process.returncode:
   print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
  if name=='close':print(process.stdout.decode().splitlines()[-1])
finally:
 for path in [stage,*stage.iterdir()]:path.chmod(path.stat().st_mode&~0o222)
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                      input=json.dumps(payload).encode(),capture_output=True)
if result.returncode:
    print('Retained stage:',stage);print(result.stderr.decode());raise SystemExit(result.returncode)
receipt=json.loads(result.stdout)
with (HERE/'t16_r022_close_receipt.json').open('x',encoding='utf-8') as stream:
    json.dump({'stage':stage,**receipt},stream,indent=2);stream.write('\n')
print(json.dumps(receipt,indent=2))
