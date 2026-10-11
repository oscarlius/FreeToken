"""Read-only monitor of R022's frozen process handle; never restarts a run."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
launch = HERE/'t16_d14_E2-R022-gate-D14_launch_receipt.json'
receipt = json.loads(launch.read_text())
identity = HERE/'t16_d14_R022_process_identity.json'
ticks = json.loads(identity.read_text())['start_ticks'] if identity.exists() else None
program = "receipt="+repr(receipt)+"\nexpected_ticks="+repr(ticks)+"\n"+r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken');directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/receipt['rid']
actual=json.loads((root/'runs/dev_D14'/('launch_'+receipt['rid']+'.json')).read_text());assert actual==receipt
proc=pathlib.Path('/proc')/str(receipt['batch_pid']);handle={'pid':receipt['batch_pid'],'present':proc.exists()}
if proc.exists():
 fields=(proc/'stat').read_text().rpartition(') ')[2].split();argv=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
 handle.update(state=fields[0],pgid=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]))
 assert handle['pgid']==handle['session']==receipt['batch_pgid'] and receipt['frozen_runner'] in argv
 assert expected_ticks is None or expected_ticks==handle['start_ticks']
status=json.loads((directory/('status_batch'+str(receipt['batch'])+'.json')).read_text())
assert status['rid']==receipt['rid'] and status['batch_pid']==receipt['batch_pid']
lock=pathlib.Path('/data2/_shared/gpu.lock');arms=[]
for arm in sorted(p for p in directory.iterdir() if p.is_dir()):
 log=arm/'serve.log';tail=log.read_text(errors='replace').splitlines()[-4:] if log.exists() else []
 arms.append({'name':arm.name,'files':{n:(arm/n).stat().st_size for n in ['det.json','tax.json','d0_prefill.jsonl'] if (arm/n).exists()},'tail':tail})
print(json.dumps({'handle':handle,'status':status,'lock':json.loads(lock.read_text()) if lock.exists() else None,
 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader']).decode().strip(),'arms':arms},indent=2))
'''
process=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],capture_output=True)
if process.returncode:
    print(process.stderr.decode());raise SystemExit(process.returncode)
record=json.loads(process.stdout)
if not identity.exists() and record['handle'].get('start_ticks'):
    with identity.open('x',encoding='utf-8') as stream:
        json.dump({'launch_sha256':hashlib.sha256(launch.read_bytes()).hexdigest(),**record['handle']},stream,indent=2);stream.write('\n')
print(json.dumps(record,indent=2))
