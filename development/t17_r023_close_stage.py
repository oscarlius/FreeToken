"""Freeze Linux closure tests and raw review, then close only the exact R023."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
RECEIPT = HERE / 't17_r023_close_cpu_receipt.json'
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage'])
if data['close']:
 report=stage/'closure_cpu.json'
 if report.is_symlink() or hashlib.sha256(report.read_bytes()).hexdigest()!=data['report_sha256']:
  raise ValueError('staged closure CPU receipt changed')
 cpu=json.loads(report.read_text())
 for name,digest in cpu['source_files'].items():
  path=stage/name
  if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
   raise ValueError('frozen closure source changed: '+name)
 process=subprocess.run([sys.executable,str(stage/'t17_r023_close.py'),'--close'],capture_output=True,
  env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''})
 if process.returncode:
  print(process.stdout.decode(),file=sys.stderr);print(process.stderr.decode(),file=sys.stderr)
  raise SystemExit(process.returncode)
 print(process.stdout.decode().splitlines()[-1]);raise SystemExit(0)
stage.mkdir(exist_ok=False)
for name,value in data['files'].items():
 path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as stream:stream.write(base64.b64decode(value))
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''}
try:
 test=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
  str(stage/'tests/test_round_close.py'),str(stage/'tests/test_round_json_append.py')],
  cwd=stage,capture_output=True,env=env)
 (stage/'tests.log').write_bytes(test.stdout+test.stderr)
 if test.returncode:
  print((test.stdout+test.stderr).decode(),file=sys.stderr);raise SystemExit(test.returncode)
 cpu={'schema':'ft_t17_r023_closure_cpu/v1','returncode':test.returncode,'gpu_started':False,
  'close_sha256':hashlib.sha256((stage/'round_close.py').read_bytes()).hexdigest(),
  'tests_log_sha256':hashlib.sha256((stage/'tests.log').read_bytes()).hexdigest(),
  'source_files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in data['files']}}
 (stage/'closure_cpu.json').write_text(json.dumps(cpu,indent=2)+'\n')
 audit=subprocess.run([sys.executable,str(stage/'t17_r023_close.py')],capture_output=True,env=env)
 (stage/'audit.log').write_bytes(audit.stdout+audit.stderr)
 if audit.returncode:
  print((audit.stdout+audit.stderr).decode(),file=sys.stderr);raise SystemExit(audit.returncode)
 review=json.loads(audit.stdout);(stage/'review.json').write_text(json.dumps(review,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps({'stage':str(stage),'report_sha256':hashlib.sha256((stage/'closure_cpu.json').read_bytes()).hexdigest(),
  'review_sha256':hashlib.sha256((stage/'review.json').read_bytes()).hexdigest(),
  'tests':test.stdout.decode().strip().splitlines()[-1],
  'rid':review['rid'],'proposed_verdict':review['proposed_verdict'],
  'original_raw_files':len(review['original_raw_files']),
  'first_token_fork':review['observed']['first_token_fork']}))
finally:
 for path in [stage,*stage.rglob('*')]:path.chmod(path.stat().st_mode&~0o222)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    if args.close:
        receipt = json.loads(RECEIPT.read_text(encoding='utf-8'))
        payload = {'close': True, 'stage': receipt['stage'], 'report_sha256': receipt['report_sha256']}
    else:
        files = {name: (HERE / name).read_bytes() for name in ('t17_r023_read.py', 't17_r023_close.py')}
        files.update({name: (HERE.parent / 'scripts' / name).read_bytes()
                      for name in ('round_json_append.py', 'round_close.py', 'round_close.sh')})
        files.update({'tests/' + name: (HERE.parent / 'scripts/tests' / name).read_bytes()
                      for name in ('test_round_close.py', 'test_round_json_append.py')})
        identity = hashlib.sha256(b''.join(name.encode() + files[name] for name in sorted(files))).hexdigest()
        payload = {'close': False, 'stage': '/data2/FreeToken/runs/dev_D14/r023_close_' + identity[:12],
                   'files': {name: base64.b64encode(value).decode() for name, value in files.items()}}
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '9', '/data2/FreeToken/venv/bin/python',
                              '-c', shlex.quote(PROGRAM)], input=json.dumps(payload).encode(), capture_output=True)
    if process.returncode:
        print('Retained stage:', payload['stage'])
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    receipt = json.loads(process.stdout)
    target = HERE / 't17_r023_close_receipt.json' if args.close else RECEIPT
    with target.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
