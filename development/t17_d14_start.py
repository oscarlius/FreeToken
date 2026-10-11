"""Controller for an exact CPU receipt; preflight by default, launch explicitly."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
options=argparse.ArgumentParser(description=__doc__)
options.add_argument('--launch',action='store_true')
args=options.parse_args()
receipt=json.loads((HERE/'t17_d14_cpu_receipt.json').read_text(encoding='utf-8'))
for name,digest in receipt['report']['source_files'].items():
    if name in ('t17_d14_startup.py','t17_d14_exact_ids.py','real_inputs.json','stage_source.py'):continue
    path=HERE/name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise ValueError('local reviewed source differs from CPU receipt: '+name)
payload={'stage':receipt['stage'],'cpu_sha256':receipt['report_sha256'],'source_files':receipt['report']['source_files'],'launch':args.launch}
PROGRAM=r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage'])
if stage.is_symlink() or hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest()!=data['cpu_sha256']:
 raise ValueError('CPU receipt changed')
report=json.loads((stage/'cpu_validation.json').read_text())
if report['source_files']!=data['source_files']:raise ValueError('CPU file list changed')
for name,digest in data['source_files'].items():
 if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=digest:raise ValueError('reviewed file changed')
root=pathlib.Path('/data2/FreeToken/runs/dev_D14')
if data['launch']:
 for path in root.glob('launch_E2-R*-gate-T17.json'):
  old=json.loads(path.read_text());round_root=pathlib.Path('/data2/_shared/runs/ft_rounds')/old['rid']
  status=round_root/('status_batch'+str(old['batch'])+'.json')
  if not status.is_file() or json.loads(status.read_text()).get('state') not in ('failed','complete_measurements_pending_review'):
   raise ValueError('existing T17 receipt is not terminal; no restart allowed')
  if old.get('source_stage')==str(stage):raise ValueError('this frozen stage was already launched')
argv=[sys.executable,str(stage/'t17_d14_launch.py'),'--stage',str(stage)]
if data['launch']:argv.append('--launch')
process=subprocess.run(argv,capture_output=True,timeout=180)
if process.returncode:
 print(process.stdout.decode(),file=sys.stderr);print(process.stderr.decode(),file=sys.stderr);raise SystemExit(process.returncode)
lines=process.stdout.decode().splitlines();print(lines[-1])
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                      input=json.dumps(payload).encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode());raise SystemExit(result.returncode)
out=json.loads(result.stdout)
if args.launch:
    with (HERE/('t17_d14_'+out['rid']+'_launch_receipt.json')).open('x',encoding='utf-8') as stream:
        json.dump(out,stream,indent=2);stream.write('\n')
else:
    (HERE/'t17_d14_preflight.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
