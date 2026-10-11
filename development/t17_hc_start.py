"""Launch only the independently reviewed hc CPU stage and retain its receipt."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
cpu_path = HERE / 't17_hc_cpu_a5ba447e30df.json'
cpu = json.loads(cpu_path.read_text(encoding='utf-8'))
EXPECTED = '5f4d5582f5786e7c76f626dfc256386e5f813244d534fac1167a5fb5c4d77a32'
if cpu['report_sha256'] != EXPECTED or cpu['stage'] != '/data2/FreeToken/runs/dev_D14/hc_a5ba447e30df':
    raise ValueError('exact independently reviewed CPU stage required')
reused = {'t17_original_startup.py', 't17_d14_exact_ids.py', 'real_inputs.json'}
for name, digest in cpu['report']['source_files'].items():
    if name not in reused and hashlib.sha256((HERE / name).read_bytes()).hexdigest() != digest:
        raise ValueError('local source changed after review: ' + name)
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage'])
if hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest()!=data['expected']:
 raise ValueError('actual CPU report changed')
process=subprocess.run([sys.executable,str(stage/'t17_hc_launch.py'),'--stage',str(stage),
 '--report-sha256',data['expected']],capture_output=True)
if process.returncode:
 print(process.stdout.decode(),file=sys.stderr);print(process.stderr.decode(),file=sys.stderr);raise SystemExit(process.returncode)
receipt=json.loads(process.stdout.decode().splitlines()[-1]);print(json.dumps(receipt))
'''
process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9', '/data2/FreeToken/venv/bin/python',
                          '-'],
                         input=('import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps({'stage': cpu['stage'], 'expected': EXPECTED}))+')\n'+PROGRAM).encode(), capture_output=True)
if process.returncode:
    print(process.stderr.decode())
    raise SystemExit(process.returncode)
receipt = json.loads(process.stdout)
if (receipt.get('state') != 'launched' or receipt.get('diagnostic_only') is not True
        or receipt.get('cpu_stage_sha256') != EXPECTED or receipt.get('source_files') != cpu['report']['source_files']
        or receipt.get('FT_LM_CHUNK') != 4096):
    raise ValueError('actual hc launch receipt differs; inspect server receipt before any retry')
with (HERE / ('t17_hc_' + receipt['rid'] + '_launch_receipt.json')).open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps(receipt, indent=2))
