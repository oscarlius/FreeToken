"""Freeze the release tool, run Linux tests, and prepare a real immutable-data review."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import runpy

ROOT = Path(__file__).resolve().parents[1]
files = {name: (ROOT/name).read_bytes() for name in (
    'development/ftd_release_20261004.py', 'development/test_ftd_release_20261004.py',
    'scripts/round_json_append.py')}
namespace = runpy.run_path(str(ROOT/'development/ftd_release_20261004.py'))
for item in namespace['FAILED_RESULT_DOCUMENTS'].values():
    files[item['path']] = (ROOT/item['path']).read_bytes()
identity = hashlib.sha256(b''.join(name.encode()+data for name,data in sorted(files.items()))).hexdigest()
payload = {'stage': '/data2/FreeToken/runs/dev_P0/release_'+identity[:12],
           'files': {name:base64.b64encode(data).decode() for name,data in files.items()}}
program = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(parents=True,exist_ok=False)
for name,value in data['files'].items():
 path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as stream:stream.write(base64.b64decode(value))
 path.chmod(0o444)
for name in ('development','scripts'):(stage/name).chmod(0o555)
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''}
test=subprocess.run([sys.executable,str(stage/'development/test_ftd_release_20261004.py')],capture_output=True,env=env)
(stage/'linux_tests.log').write_bytes(test.stdout+test.stderr)
if test.returncode:
 print((test.stdout+test.stderr).decode(),file=sys.stderr);raise SystemExit(test.returncode)
process=subprocess.run([sys.executable,str(stage/'development/ftd_release_20261004.py'),'--mode','prepare',
 '--out',str(stage/'review.json'),'--release-out',str(stage/'proposal.json')],capture_output=True,env=env)
(stage/'prepare.log').write_bytes(process.stdout+process.stderr)
if process.returncode:
 print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
review=json.loads((stage/'review.json').read_text())
print(json.dumps({'stage':str(stage),'tool_sha256':hashlib.sha256((stage/'development/ftd_release_20261004.py').read_bytes()).hexdigest(),
 'review_sha256':hashlib.sha256((stage/'review.json').read_bytes()).hexdigest(),'proposal_sha256':hashlib.sha256((stage/'proposal.json').read_bytes()).hexdigest(),
 'linux_tests':(test.stdout+test.stderr).decode().strip(),'ready_for_apply':review['ready_for_apply'],'rounds':len(review['rounds']),
 'planned_appends':review['planned_appends'],'blocking_rounds':review['blocking_rounds'],'review':review},sort_keys=True))
'''
process = subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
                         input=json.dumps(payload).encode(),capture_output=True)
if process.returncode:
    print(process.stderr.decode());raise SystemExit(process.returncode)
receipt = json.loads(process.stdout)
with (ROOT/'development/p0_release_stage_receipt.json').open('x',encoding='utf-8') as stream:
    json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='review'},indent=2))
