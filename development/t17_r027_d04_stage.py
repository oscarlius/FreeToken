"""Create one immutable Linux CPU-only R027 D04 audit stage; never closes a round."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
FILES = ('t17_r027_d04_close.py', 't17_prefix_numeric_read.py',
         't17_r027_independent_cpu_review.py',
         't17_prefix_numeric_E2-R027-diagnostic-T17_reader_v3.json',
         'tests/test_t17_r027_d04_close.py', 'tests/test_t17_prefix_numeric_read.py')

PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
d=json.load(sys.stdin);stage=pathlib.Path(d['stage'])
if stage.exists() or stage.is_symlink() or not str(stage).startswith('/data2/FreeToken/runs/dev_D14/r027_d04_'):raise ValueError('new exact stage required')
stage.mkdir(parents=True)
try:
 for n,v in d['files'].items():
  p=stage/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(v));p.chmod(0o444)
 env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
 t=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_t17_r027_d04_close.py','tests/test_t17_prefix_numeric_read.py'],cwd=stage,env=env,capture_output=True,text=True)
 (stage/'tests.log').write_text(t.stdout+t.stderr)
 a=subprocess.run([sys.executable,'t17_r027_d04_close.py'],cwd=stage,env=env,capture_output=True,text=True)
 (stage/'audit.log').write_text(a.stdout+a.stderr)
 if t.returncode or a.returncode:raise ValueError('CPU test/audit failed')
 report={'gpu_started':False,'tests_returncode':t.returncode,'audit_returncode':a.returncode,
  'source_files':{n:hashlib.sha256((stage/n).read_bytes()).hexdigest() for n in d['files']},
  'tests_log_sha256':hashlib.sha256((stage/'tests.log').read_bytes()).hexdigest(),
  'audit_log_sha256':hashlib.sha256((stage/'audit.log').read_bytes()).hexdigest()}
 (stage/'stage_receipt.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps({'stage':str(stage),'receipt_sha256':hashlib.sha256((stage/'stage_receipt.json').read_bytes()).hexdigest(),**report}))
finally:
 for p in [stage,*stage.rglob('*')]:p.chmod(p.stat().st_mode&~0o222)
'''


def main():
    files = {name: (HERE / name).read_bytes() for name in FILES}
    identity = hashlib.sha256(b''.join(name.encode() + files[name] for name in sorted(files))).hexdigest()
    data = {'stage': '/data2/FreeToken/runs/dev_D14/r027_d04_' + identity[:12],
            'files': {name: base64.b64encode(raw).decode() for name, raw in files.items()}}
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(data)) + ')\n' + PROGRAM
    result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9','/data2/FreeToken/venv/bin/python','-'],
                            input=wire.encode(),capture_output=True)
    if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace'))
    receipt = json.loads(result.stdout)
    target = HERE / 't17_r027_d04_stage_v3_receipt.json'
    with target.open('x',encoding='utf-8') as f: json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(receipt,sort_keys=True))

if __name__ == '__main__': main()
