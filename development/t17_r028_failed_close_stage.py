"""Freeze the exact R028 failure CPU audit before its separately reviewed closure."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
RECEIPT = HERE / 't17_r028_failed_close_cpu_receipt.json'
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage'])
if not str(stage).startswith('/data2/FreeToken/runs/dev_D14/r028_failed_close_') or stage.is_symlink():
 raise ValueError('exact new closure stage required')
if data['close']:
 if hashlib.sha256((stage/'closure_cpu.json').read_bytes()).hexdigest()!=data['report_sha256']:
  raise ValueError('frozen R028 CPU report changed')
 report=json.loads((stage/'closure_cpu.json').read_bytes())
 if report['gpu_started'] is not False or report['returncode']!=0:raise ValueError('successful CPU-only report required')
 for name,digest in report['source_files'].items():
  path=stage/name
  if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
   raise ValueError('frozen closure source changed')
 if hashlib.sha256((stage/'review.json').read_bytes()).hexdigest()!=data['review_sha256']:
  raise ValueError('separately reviewed raw CPU evidence changed')
 process=subprocess.run([sys.executable,str(stage/'t17_r028_failed_close.py'),'--close'],capture_output=True,
   env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'})
 if process.returncode:print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
 print(process.stdout.decode());raise SystemExit(0)
stage.mkdir()
try:
 for name,encoded in data['files'].items():
  path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(base64.b64decode(encoded));path.chmod(0o444)
 env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
 compile_process=subprocess.run([sys.executable,'-c',
  'import ast,pathlib;[ast.parse(p.read_bytes(),filename=str(p)) for p in pathlib.Path(".").glob("*.py")]'],
  cwd=stage,env=env,capture_output=True)
 (stage/'compile.log').write_bytes(compile_process.stdout+compile_process.stderr)
 if compile_process.returncode:raise ValueError('closure CPU syntax validation failed')
 process=subprocess.run([sys.executable,str(stage/'t17_r028_failed_close.py')],env=env,capture_output=True)
 (stage/'audit.log').write_bytes(process.stdout+process.stderr)
 if process.returncode:print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
 review=json.loads(process.stdout);(stage/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
 report={'schema':'ft_t17_r028_closure_cpu/v1','gpu_started':False,'returncode':0,
  'compile_log_sha256':hashlib.sha256((stage/'compile.log').read_bytes()).hexdigest(),
  'audit_log_sha256':hashlib.sha256((stage/'audit.log').read_bytes()).hexdigest(),
  'source_files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in data['files']},
  'retained_D04_exact_source_tests':'r023_close_cc5852e4750a; verified SHA and log without unnecessary rerun'}
 (stage/'closure_cpu.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'stage':str(stage),'report_sha256':hashlib.sha256((stage/'closure_cpu.json').read_bytes()).hexdigest(),
  'review_sha256':hashlib.sha256((stage/'review.json').read_bytes()).hexdigest(),'rid':review['rid'],
  'original_raw_files':len(review['original_raw_files']),'diagnostic_only':True,
  'measurements_completed':review['measurements_completed'],
  'source_files':report['source_files']}))
finally:
 for path in [stage,*stage.rglob('*')]:path.chmod(path.stat().st_mode&~0o222)
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--close', action='store_true')
    parser.add_argument('--receipt', type=Path, default=RECEIPT)
    options = parser.parse_args()
    receipt_target = HERE / options.receipt
    if options.close:
        receipt = json.loads(receipt_target.read_text(encoding='utf-8'))
        data = {'close': True, 'stage': receipt['stage'], 'report_sha256': receipt['report_sha256'],
                'review_sha256': receipt['review_sha256']}
    else:
        files = {name: (HERE / name).read_bytes() for name in ('t17_r028_failed_close.py', 't17_r028_failed_close_stage.py')}
        files.update({name: (HERE.parent / 'scripts' / name).read_bytes()
                      for name in ('round_json_append.py', 'round_close.py', 'round_close.sh')})
        identity = hashlib.sha256(b''.join(name.encode() + files[name] for name in sorted(files))).hexdigest()
        data = {'close': False, 'stage': '/data2/FreeToken/runs/dev_D14/r028_failed_close_' + identity[:12],
                'files': {name: base64.b64encode(value).decode() for name, value in files.items()}}
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(data)) + ')\n' + PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode('utf-8'), capture_output=True)
    if process.returncode:
        print('Retained stage:', data['stage'])
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    result = json.loads(process.stdout)
    target = HERE / 't17_r028_failed_close_receipt.json' if options.close else receipt_target
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
