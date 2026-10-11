"""Read the exact numeric diagnostic process, source and service identities."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
PROGRAM=r'''
import hashlib,json,pathlib,subprocess,sys
receipt=json.load(sys.stdin);rid=receipt['rid'];batch=receipt['batch'];root=pathlib.Path('/data2/FreeToken')
r=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
if json.loads((root/'runs/dev_D14'/('launch_'+rid+'.json')).read_bytes())!=receipt:raise ValueError('reservation receipt changed')
stage=pathlib.Path(receipt['frozen_runner']).parent
for name,digest in receipt['source_files'].items():
 p=stage/name
 if p.is_symlink() or p.stat().st_mode&0o222 or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('frozen source changed')
def handle(identity):
 p=pathlib.Path('/proc')/str(identity['pid'])/'stat'
 if not p.exists():return {'pid':identity['pid'],'present':False}
 fields=p.read_text().rpartition(') ')[2].split()
 if int(fields[19])!=identity['start_ticks']:raise ValueError('captured process birth reused')
 return {'pid':identity['pid'],'present':True,'state':fields[0],'birth_ticks':int(fields[19]),'pgid':int(fields[2]),'session':int(fields[3])}
status_path=r/('status_batch'+str(batch)+'.json')
status=json.loads(status_path.read_bytes()) if status_path.exists() else None
batch_handle=handle({'pid':receipt['batch_pid'],'start_ticks':status['batch_start_ticks']}) if status else None
arms=[]
for name in ('numeric_warm','numeric_cold'):
 arm=r/name
 if not arm.exists():continue
 identity=arm/'process_identity.json';stopped=arm/'stop_identity.json';log=arm/'serve.log'
 finals=[{'path':p.name,'value':json.loads(p.read_bytes())} for p in sorted((arm/'numeric').glob('final_*.json'))]
 arms.append({'name':name,'service':handle(json.loads(identity.read_bytes())) if identity.exists() else None,
              'stopped':json.loads(stopped.read_bytes()) if stopped.exists() else None,'finals':finals,
              'tail':log.read_text(errors='replace').splitlines()[-5:] if log.exists() else []})
lock=pathlib.Path('/data2/_shared/gpu.lock')
print(json.dumps({'rid':rid,'batch':batch,'status':status,'handle':batch_handle,'arms':arms,
                 'lock':json.loads(lock.read_bytes()) if lock.exists() else None,
                 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip(),
                 'measurement':(r/('diagnostic_batch'+str(batch)+'.json')).exists()}))
'''
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('rid');options=parser.parse_args()
    if '/' in options.rid or '\\' in options.rid:raise ValueError('one exact RID required')
    receipt=json.loads((HERE/('t17_prefix_numeric_'+options.rid+'_launch_receipt.json')).read_bytes())
    if receipt['schema']!='ft_t17_prefix_numeric_launch/v1' or receipt['rid']!=options.rid:raise ValueError('numeric receipt required')
    result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                          input=json.dumps(receipt).encode(),capture_output=True)
    if result.returncode:print(result.stderr.decode());raise SystemExit(result.returncode)
    print(json.dumps(json.loads(result.stdout),indent=2))
