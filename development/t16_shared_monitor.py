"""Read one exact shared T16 launch; never launch, stop, or alter a round."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys
receipt=json.load(sys.stdin)
root=pathlib.Path('/data2/FreeToken')
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/receipt['rid']
server=root/('runs/dev_'+receipt['card'])/('launch_'+receipt['rid']+'.json')
if json.loads(server.read_text())!=receipt:raise ValueError('server/controller receipt differs')
stage=pathlib.Path(receipt['source_stage']);execution=pathlib.Path(receipt['frozen_runner']).parent
report=stage/'cpu_validation.json'
if hashlib.sha256(report.read_bytes()).hexdigest()!=receipt['cpu_stage_sha256']:
 raise ValueError('frozen CPU proof changed')
for name,digest in json.loads(report.read_text())['files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
  raise ValueError('frozen execution source changed: '+name)
pid=receipt['batch_pid'];proc=pathlib.Path('/proc')/str(pid)
handle={'pid':pid,'present':proc.exists()}
if proc.exists():
 fields=(proc/'stat').read_text().rpartition(') ')[2].split()
 handle.update(state=fields[0],pgid=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]))
 if any(handle[k]!=receipt['process_identity'][k] for k in ('pid','pgid','session','start_ticks')):
  raise ValueError('reserved process identity changed')
 if fields[0]!='Z':
  argv=(proc/'cmdline').read_bytes().split(b'\0')
  if receipt['frozen_runner'].encode() not in argv or receipt['rid'].encode() not in argv or b'--run' not in argv:
   raise ValueError('live process is not the exact frozen runner')
status_path=directory/('status_batch'+str(receipt['batch'])+'.json')
status=json.loads(status_path.read_text()) if status_path.exists() else None
if status and (status['rid']!=receipt['rid'] or status['batch_pid']!=pid):
 raise ValueError('status belongs to another launch')
lock=pathlib.Path('/data2/_shared/gpu.lock');arms=[]
for arm in sorted(p for p in directory.iterdir() if p.is_dir() and (p/'serve.log').exists()):
 arms.append({'name':arm.name,'receipts':[p.name for p in arm.glob('*.json')],
              'tail':(arm/'serve.log').read_text(errors='replace').splitlines()[-3:]})
print(json.dumps({'rid':receipt['rid'],'batch':receipt['batch'],'handle':handle,'status':status,
 'lock':json.loads(lock.read_text()) if lock.exists() else None,
 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip(),
 'arms':arms},ensure_ascii=False))
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt',type=Path)
    receipt=json.loads(parser.parse_args().receipt.read_text(encoding='utf-8'))
    result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                          input=json.dumps(receipt).encode(),capture_output=True)
    if result.returncode:
        print(result.stderr.decode());raise SystemExit(result.returncode)
    print(json.dumps(json.loads(result.stdout),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
