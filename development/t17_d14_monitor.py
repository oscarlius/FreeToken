"""Read only the exact T17 receipt, process, raw status and owned arm logs."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
receipts=list(HERE.glob('t17_d14_E2-R*-gate-T17_launch_receipt.json'))
if not receipts:raise ValueError('no root-assigned T17 launch receipt')
path=max(receipts,key=lambda p:int(p.name.split('E2-R')[1][:3]))
receipt=json.loads(path.read_text(encoding='utf-8'))
identity_path=HERE/(receipt['rid']+'_process_identity.json')
prior=json.loads(identity_path.read_text()) if identity_path.exists() else None
PROGRAM=r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin);receipt=data['receipt'];prior=data['prior']
rid=receipt['rid'];batch=receipt['batch'];pid=receipt['batch_pid']
server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json')
if json.loads(server.read_text())!=receipt:raise ValueError('controller/server receipt differs')
execution=pathlib.Path(receipt['frozen_runner']).parent
for name,digest in receipt['source_files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
  raise ValueError('frozen source differs: '+name)
proc=pathlib.Path('/proc')/str(pid)
handle={'pid':pid,'present':proc.exists()}
if proc.exists():
 fields=(proc/'stat').read_text().rpartition(') ')[2].split()
 handle.update(state=fields[0],pgid=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]))
 if fields[0]!='Z':
  command=(proc/'cmdline').read_bytes().split(b'\0')
  if (handle['pgid']!=pid or handle['session']!=pid or receipt['frozen_runner'].encode() not in command
      or rid.encode() not in command or b'--run' not in command):raise ValueError('live owned process identity differs')
 if prior and any(handle.get(k)!=prior.get(k) for k in ('pid','pgid','session','start_ticks')):
  raise ValueError('observed batch identity changed')
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
status_path=directory/('status_batch'+str(batch)+'.json')
status=json.loads(status_path.read_text()) if status_path.exists() else None
lock=pathlib.Path('/data2/FreeToken/runs/gpu.lock')
# Read the shared base's actual declaration, rather than guessing another path.
import runpy
decl=runpy.run_path(str(execution/'t16_full_tail_base_runner.py'),run_name='t17_monitor_read_only_protocol')
lock=decl['LOCK'];lock_value=json.loads(lock.read_text()) if lock.exists() else None
arms=[]
if directory.exists():
 for arm in sorted(p for p in directory.iterdir() if p.is_dir() and (p/'serve.log').exists()):
  arms.append({'name':arm.name,'receipts':[p.name for p in arm.glob('*.json')],
               'tail':(arm/'serve.log').read_text(errors='replace').splitlines()[-3:]})
print(json.dumps({'rid':rid,'batch':batch,'handle':handle,'status':status,'lock':lock_value,
 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip(),
 'arms':arms},ensure_ascii=False))
'''
out=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                   input=json.dumps({'receipt':receipt,'prior':prior}).encode(),capture_output=True)
if out.returncode:print(out.stderr.decode());raise SystemExit(out.returncode)
snapshot=json.loads(out.stdout)
handle=snapshot['handle']
if prior is None and handle.get('present') and handle.get('state')!='Z':
    with identity_path.open('x',encoding='utf-8') as stream:json.dump(handle,stream,indent=2);stream.write('\n')
print(json.dumps(snapshot,ensure_ascii=False,indent=2))
