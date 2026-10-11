"""Freeze the bridge tests and exact closure sources before authorized sync/append."""
import argparse,base64,hashlib,json,shlex,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--close',action='store_true');parser.add_argument('--receipt',default='close_cpu_receipt.json');args=parser.parse_args()
if args.close:
    receipt=json.loads((HERE/args.receipt).read_bytes())
    payload={'close':True,**receipt}
else:
    files={name:(HERE/name).read_bytes() for name in ('close.py','publication.py','test_publication.py','measure_receipt.json','benchmark_client_previous.py',
                                                   'test_benchmark_standard.py','benchmark_standard_cleanup_plan.md')}
    files['benchmark_client.py']=(ROOT.parent/'_shared/benchmark_client.py').read_bytes()
    files['evaluator.py']=(ROOT.parent/'_shared/evaluator.py').read_bytes()
    files['regrade_paper_headroom.py']=(ROOT.parent/'_shared/regrade_paper_headroom.py').read_bytes()
    for name in ('round_json_append.py','round_close.py','round_close.sh'):files[name]=(ROOT/'scripts'/name).read_bytes()
    identity=hashlib.sha256(b''.join(name.encode()+files[name] for name in sorted(files))).hexdigest()
    payload={'close':False,'stage':'/data2/FreeToken/runs/quality_close_'+identity[:12],
             'files':{name:base64.b64encode(value).decode() for name,value in files.items()}}

PROGRAM=r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
payload=json.load(sys.stdin);stage=pathlib.Path(payload['stage'])
env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1','FT_QUALITY_BENCHMARK_SOURCE':str(stage/'benchmark_client.py')}
if payload['close']:
 if hashlib.sha256((stage/'bridge_cpu.json').read_bytes()).hexdigest()!=payload['cpu_receipt_sha256']:
  raise ValueError('bridge CPU receipt changed')
 report=json.loads((stage/'bridge_cpu.json').read_bytes())
 for name,digest in report['files'].items():
  path=stage/name
  if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
   raise ValueError('closure source changed')
 result=subprocess.run([sys.executable,str(stage/'close.py')],capture_output=True,env=env)
 if result.returncode:print((result.stdout+result.stderr).decode(),file=sys.stderr);raise SystemExit(result.returncode)
 print(result.stdout.decode().splitlines()[-1]);raise SystemExit(0)
stage.mkdir(exist_ok=False)
for name,value in payload['files'].items():
 with (stage/name).open('xb') as stream:stream.write(base64.b64decode(value))
try:
 test=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'test_benchmark_standard.py'),str(stage/'test_publication.py')],
                     cwd=stage,capture_output=True,env=env)
 (stage/'bridge_tests.log').write_bytes(test.stdout+test.stderr)
 if test.returncode:print((test.stdout+test.stderr).decode(),file=sys.stderr);raise SystemExit(test.returncode)
 report={'schema':'ft_quality_bridge_cpu/v1','returncode':0,'gpu_started':False,
         'benchmark_client_sha256':hashlib.sha256((stage/'benchmark_client.py').read_bytes()).hexdigest(),
         'test_log_sha256':hashlib.sha256((stage/'bridge_tests.log').read_bytes()).hexdigest(),
         'files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in payload['files']}}
 (stage/'bridge_cpu.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'stage':str(stage),'cpu_receipt_sha256':hashlib.sha256((stage/'bridge_cpu.json').read_bytes()).hexdigest(),
                   'tests':test.stdout.decode().strip().splitlines()[-1],
                   'benchmark_client_sha256':report['benchmark_client_sha256']}))
finally:
 for path in [stage,*stage.rglob('*')]:path.chmod(path.stat().st_mode&~0o222)
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(PROGRAM)],
                      input=json.dumps(payload).encode(),capture_output=True)
if result.returncode:print('Retained stage:',payload['stage']);print(result.stderr.decode());raise SystemExit(result.returncode)
receipt=json.loads(result.stdout)
name='close_receipt.json' if args.close else args.receipt
with (HERE/name).open('x',encoding='utf-8') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
