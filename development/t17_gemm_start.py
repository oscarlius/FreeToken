"""Launch the exact reviewed Linux GDN CPU stage once and retain the actual receipt."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
EXPECTED = 'dcbb21c2df0b49cdd25311375431f6f7250ce8b6873688c8d8a38ba4faf55e56'
STAGE = '/data2/FreeToken/runs/dev_D14/gemm_e1154756dd3c'
cpu = json.loads((HERE / 't17_gemm_cpu_e1154756dd3c.json').read_bytes())
if cpu['report_sha256'] != EXPECTED or cpu['stage'] != STAGE:
    raise ValueError('exact reviewed GDN CPU stage required')
for name, digest in cpu['report']['source_files'].items():
    if name != 'plan.json' and hashlib.sha256((HERE / name).read_bytes()).hexdigest() != digest:
        raise ValueError('local source changed after review: ' + name)
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage'])
if hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest()!=data['expected']:
 raise ValueError('reviewed CPU report changed')
p=subprocess.run([sys.executable,str(stage/'t17_gemm_launch.py'),'--stage',str(stage),
 '--report-sha256',data['expected']],capture_output=True)
if p.returncode:
 print(p.stdout.decode(),file=sys.stderr);print(p.stderr.decode(),file=sys.stderr);raise SystemExit(p.returncode)
print(json.dumps(json.loads(p.stdout.decode().splitlines()[-1])))
'''
wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps({'stage': STAGE, 'expected': EXPECTED})) + ')\n' + PROGRAM
process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                          '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True)
if process.returncode:
    raise RuntimeError(process.stderr.decode() or process.stdout.decode())
receipt = json.loads(process.stdout)
if (receipt.get('state') != 'launched' or receipt.get('diagnostic_only') is not True
        or receipt.get('cpu_stage_sha256') != EXPECTED or receipt.get('source_files') != cpu['report']['source_files']
        or receipt.get('operator_only') is not True or receipt.get('operator') != 'gdn'):
    raise ValueError('launch receipt differs; inspect server receipt before any retry')
with (HERE / ('t17_gemm_' + receipt['rid'] + '_launch_receipt.json')).open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt, indent=2))
