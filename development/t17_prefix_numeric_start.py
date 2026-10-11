"""Launch the independently reviewed numeric stage once and retain its receipt."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
cpu=json.loads((HERE/'t17_prefix_numeric_cpu_65b32b3fc54a.json').read_bytes())
EXPECTED='85cf811e1d0d91c8c6e6e0dbd826edfc80a9793f7061b3cb7e4f653a8148ec7c'
if cpu['report_sha256']!=EXPECTED or cpu['stage']!='/data2/FreeToken/runs/dev_D14/prefix_numeric_65b32b3fc54a':
    raise ValueError('exact reviewed numeric CPU stage required')
for name,digest in cpu['report']['source_files'].items():
    if name not in {'t17_original_startup.py','t17_d14_exact_ids.py','real_inputs.json'}:
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:raise ValueError('source changed after CPU proof: '+name)
PROGRAM=r'''
import json,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage'])
process=subprocess.run([sys.executable,str(stage/'t17_prefix_numeric_launch.py'),'--stage',str(stage),
 '--report-sha256',data['expected']],capture_output=True)
if process.returncode:
 print(process.stdout.decode(),file=sys.stderr);print(process.stderr.decode(),file=sys.stderr);raise SystemExit(process.returncode)
print(process.stdout.decode().splitlines()[-1])
'''
process=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                      input=json.dumps({'stage':cpu['stage'],'expected':EXPECTED}).encode(),capture_output=True)
if process.returncode:print(process.stderr.decode());raise SystemExit(process.returncode)
receipt=json.loads(process.stdout)
if (receipt['state']!='launched' or receipt['diagnostic_only'] is not True or receipt['cpu_stage_sha256']!=EXPECTED
        or receipt['source_files']!=cpu['report']['source_files'] or receipt['FT_LM_CHUNK']!=4096):
    raise ValueError('actual reservation differs; inspect server receipt before any retry')
with (HERE/('t17_prefix_numeric_'+receipt['rid']+'_launch_receipt.json')).open('x',encoding='utf-8') as stream:
    json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps(receipt,indent=2))
