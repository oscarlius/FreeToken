"""Read the exact R033 batch identity and compact progress without mutating it."""
import subprocess
import argparse
import json

PROGRAM = r'''
import json,pathlib,subprocess
rid='__RID__'
root=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
identity=json.loads((pathlib.Path('/data2/FreeToken/runs/dev_D16')/('launch_'+rid+'_identity.json')).read_bytes())
receipt=json.loads((pathlib.Path('/data2/FreeToken/runs/dev_D16')/('launch_'+rid+'.json')).read_bytes())
p=pathlib.Path('/proc')/str(identity['pid'])/'stat'
live=False;state=None
if p.exists():
 s=p.read_text();t=s[s.rfind(')')+2:].split()
 if int(t[19])!=identity['start_ticks'] or int(t[2])!=identity['pgid']:raise ValueError('batch process identity changed')
 state=t[0];live=state not in ('Z','X')
status=json.loads((root/('status_batch'+str(receipt['batch'])+'.json')).read_bytes())
arm=root/status.get('arm','')
log=arm/'serve.log'
text=log.read_text(errors='replace') if log.is_file() else ''
output={'batch_alive':live,'process_state':state,'status':status,
 'case_files':len(list((root/'cases').glob('*.json'))) if (root/'cases').is_dir() else 0,
 'serve_log_tail':text[-1300:],
 'batch_log_tail':pathlib.Path(receipt['batch_log']).read_text(errors='replace')[-1400:]}
for name in ('result.json','failed_harness.json'):
 if (root/name).is_file():output[name]=json.loads((root/name).read_bytes())
print(json.dumps(output))
'''

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid', choices=('E2-R033','E2-R034','E2-R034a'), default='E2-R033')
    parser.add_argument('--compact',action='store_true')
    args=parser.parse_args()
    p = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                        '9', '/data2/FreeToken/venv/bin/python', '-'],
                       input=PROGRAM.replace('__RID__',args.rid).encode(), capture_output=True)
    if args.compact and p.returncode==0:
        value=json.loads(p.stdout)
        print(json.dumps({k:v for k,v in value.items() if k not in ('serve_log_tail','batch_log_tail')}))
    else:
        print(p.stdout.decode())
    if p.stderr:print(p.stderr.decode())
    raise SystemExit(p.returncode)
