"""Read a specifically launched matched diagnostic without process or round mutations."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys
receipt=json.load(sys.stdin)
rid=receipt['rid'];batch=receipt['batch'];pid=receipt['batch_pid']
server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json')
if json.loads(server.read_text())!=receipt:raise ValueError('exact server/controller launch receipt differs')
execution=pathlib.Path(receipt['frozen_runner']).parent
for name,digest in receipt['source_files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
  raise ValueError('frozen source changed: '+name)
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
status_path=directory/('status_batch'+str(batch)+'.json')
status=json.loads(status_path.read_text()) if status_path.exists() else None
def process_handle(pid,expected=None):
 proc=pathlib.Path('/proc')/str(pid)
 handle={'pid':pid,'present':proc.exists()}
 if not handle['present']:return handle
 try:fields=(proc/'stat').read_text().rpartition(') ')[2].split()
 except FileNotFoundError:return {'pid':pid,'present':False}
 handle.update(state=fields[0],pgid=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]))
 if expected and any(handle[key]!=expected[key] for key in ['pid','pgid','session','start_ticks']):
  raise ValueError('live process birth identity differs')
 return handle
handle=process_handle(pid)
if handle.get('present') and handle['state']!='Z':
 command=(pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
 if (handle['pgid']!=pid or handle['session']!=pid or receipt['frozen_runner'].encode() not in command
     or rid.encode() not in command or b'--run' not in command):raise ValueError('live diagnostic batch differs')
 if status and status.get('batch_start_ticks')!=handle['start_ticks']:raise ValueError('batch birth receipt differs')
arms=[]
for name in ['matched_warm','matched_cold']:
 arm=directory/name
 if not arm.exists():continue
 item={'name':name,'service':None,'stopped':None,'matched':[]}
 path=arm/'process_identity.json'
 if path.exists():
  identity=json.loads(path.read_text());item['service']=process_handle(identity['pid'],identity)
 path=arm/'stop_identity.json'
 if path.exists():item['stopped']=json.loads(path.read_text())
 for path in sorted((arm/'matched').glob('final_*.json')):
  item['matched'].append({'path':path.name,'value':json.loads(path.read_text())})
 path=arm/'serve.log'
 if path.exists():item['tail']=path.read_text(errors='replace').splitlines()[-3:]
 arms.append(item)
lock=pathlib.Path('/data2/_shared/gpu.lock')
lock_value=json.loads(lock.read_text()) if lock.exists() else None
print(json.dumps({'rid':rid,'batch':batch,'handle':handle,'status':status,'lock':lock_value,'arms':arms,
 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip(),
 'result_files':[p.name for p in directory.glob('*comparison*.json')]},ensure_ascii=False))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rid')
    options = parser.parse_args()
    if not options.rid.startswith('E2-R') or not options.rid.endswith('-diagnostic-T17'):
        raise ValueError('exact diagnostic RID required')
    receipt_path = HERE / ('t17_matched_' + options.rid + '_launch_receipt.json')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt['rid'] != options.rid or receipt.get('diagnostic_only') is not True:
        raise ValueError('exact launched diagnostic receipt required')
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(PROGRAM)],
                             input=json.dumps(receipt).encode(), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    print(json.dumps(json.loads(process.stdout), ensure_ascii=False, indent=2))
