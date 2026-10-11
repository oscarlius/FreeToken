"""Stage exact failure closer + D04 tools and execute its narrowly bound closure."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
files = {'t16_r021_failed_close.py': (ROOT/'development/t16_r021_failed_close.py').read_bytes()}
files.update({name: (ROOT/'scripts'/name).read_bytes() for name in ('round_json_append.py', 'round_close.py', 'round_close.sh')})
identity = hashlib.sha256(b''.join(name.encode()+data for name,data in sorted(files.items()))).hexdigest()
payload = {'stage': '/data2/FreeToken/runs/dev_D14/r021_failed_'+identity[:12],
           'files': {name: base64.b64encode(data).decode() for name,data in files.items()}}
program = r'''
import base64,json,pathlib,subprocess,sys
data=json.load(sys.stdin); directory=pathlib.Path(data['stage']);directory.mkdir(exist_ok=False)
for name,value in data['files'].items():
 with (directory/name).open('xb') as stream:stream.write(base64.b64decode(value))
process=subprocess.run([sys.executable,str(directory/'t16_r021_failed_close.py')],capture_output=True)
(directory/'closure.log').write_bytes(process.stdout+process.stderr)
for path in [directory,*directory.iterdir()]:path.chmod(path.stat().st_mode&~0o222)
if process.returncode:
 print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
print(process.stdout.decode(),end='')
'''
result = subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
                        input=json.dumps(payload).encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode());raise SystemExit(result.returncode)
receipt = json.loads(result.stdout.decode().splitlines()[-1])
with (ROOT/'development/t16_r021_failed_close_receipt.json').open('x',encoding='utf-8') as stream:
    json.dump({'stage':payload['stage'],**receipt},stream,indent=2);stream.write('\n')
print(json.dumps(receipt,indent=2))
