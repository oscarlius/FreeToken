"""Dispatch one reviewed remote phase; transport secrets never enter receipts."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex

HERE=Path(__file__).resolve().parent
PRIVATE=HERE/'private'
spec=importlib.util.spec_from_file_location('transport',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
transport=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=['prepare','execute','verify'])
args=parser.parse_args()
client=transport.connect()
try:
    sftp=client.open_sftp()
    remote='/data2/FreeToken/development/server_finalization_20261014'
    if args.phase=='prepare':
        try:sftp.mkdir(remote,mode=0o700)
        except OSError:sftp.stat(remote)
        sftp.put(str(PRIVATE/'SERVER_INVENTORY.json'),remote+'/inventory.json')
        sftp.chmod(remote+'/inventory.json',0o600)
        sftp.put(str(HERE/'remote_cleanup.py'),remote+'/remote_cleanup.py')
        sftp.chmod(remote+'/remote_cleanup.py',0o600)
    command='nice -n 19 ionice -c 3 /data2/FreeToken/venv/bin/python '+shlex.quote(remote+'/remote_cleanup.py')+' '+args.phase
    _,out,err=client.exec_command(command)
    output,error=out.read().decode(),err.read().decode()
    status=out.channel.recv_exit_status()
    (PRIVATE/(args.phase+'.stdout.log')).write_text(output,encoding='utf-8')
    (PRIVATE/(args.phase+'.stderr.log')).write_text(error,encoding='utf-8')
    for name in ['PLAN.json','ADMISSION.json','PROGRESS.json','RESULT.json']:
        try:sftp.get('/data2/FreeToken/archive/server_finalization_20261014/'+name,str(PRIVATE/name))
        except FileNotFoundError:pass
    sftp.close()
    print(output)
    if error: print(error)
    assert status==0,status
finally:
    client.close()
