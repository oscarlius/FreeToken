"""Read one exact launched operator replay; optionally retain a local observation."""
import argparse
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys
receipt=json.load(sys.stdin);rid=receipt['rid'];batch=receipt['batch'];pid=receipt['batch_pid']
server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json')
if json.loads(server.read_bytes())!=receipt:raise ValueError('server/controller receipt differs')
frozen=pathlib.Path(receipt['frozen_runner']).parent
for name,want in receipt['source_files'].items():
 p=frozen/name
 if p.is_symlink() or p.stat().st_mode&0o222 or hashlib.sha256(p.read_bytes()).hexdigest()!=want:
  raise ValueError('frozen replay source changed: '+name)
root=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
def load(name):
 p=root/name
 if not p.exists():return None
 if p.is_symlink() or not p.is_file():raise ValueError('regular replay artifact required: '+name)
 return json.loads(p.read_bytes())
identity=load('process_identity.json');status=load('status_batch'+str(batch)+'.json')
proc=pathlib.Path('/proc')/str(pid);handle={'pid':pid,'present':False}
try:fields=(proc/'stat').read_text().rpartition(') ')[2].split()
except FileNotFoundError:pass
else:
 handle.update(present=True,state=fields[0],pgid=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]))
 if identity and any(handle[key]!=identity[key] for key in ('pid','pgid','session','start_ticks')):
  raise ValueError('replay process birth identity changed')
 if handle['state']!='Z':
  command=(proc/'cmdline').read_bytes().split(b'\0')
  if receipt['frozen_runner'].encode() not in command or rid.encode() not in command or b'--run' not in command:
   raise ValueError('live replay command differs')
if identity:
 if identity['pid']!=pid or identity['pgid']!=pid or identity['session']!=pid:raise ValueError('batch session differs')
if status:
 if status['rid']!=rid or status['batch']!=batch or status['batch_pid']!=pid:raise ValueError('status identity differs')
 if identity and status['batch_start_ticks']!=identity['start_ticks']:raise ValueError('status birth differs')
lock_path=pathlib.Path('/data2/_shared/gpu.lock');lock=json.loads(lock_path.read_bytes()) if lock_path.exists() else None
log=pathlib.Path(receipt['batch_log'])
print(json.dumps({'schema':'ft_t17_gemm_monitor/v1','rid':rid,'batch':batch,'handle':handle,'identity':identity,
 'status':status,'lock':lock,'result_present':(root/'gemm/receipt.json').is_file(),
 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip(),
 'batch_log_tail':log.read_text(errors='replace').splitlines()[-5:] if log.exists() else []}))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rid')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', args.rid):
        raise ValueError('exact operator diagnostic RID required')
    receipt = json.loads((HERE / ('t17_gemm_' + args.rid + '_launch_receipt.json')).read_bytes())
    if receipt['rid'] != args.rid or receipt.get('operator_only') is not True or receipt.get('operator') != 'gdn':
        raise ValueError('exact GDN operator launch receipt required')
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(receipt)) + ')\n' + PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True)
    if process.returncode:
        raise RuntimeError(process.stderr.decode() or process.stdout.decode())
    value = json.loads(process.stdout)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    print(json.dumps(value, indent=2))
