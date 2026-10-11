"""Freeze GDN replay sources, Linux CPU tests and real input/weight preparation."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
names = ('t17_d14_gpu.py', 't17_d14_runner.py', 't17_d14_artifacts.py', 't17_d14_observe.py',
         't17_owned_launch_protocol.py', 't16_full_tail_base_runner.py', 't17_hc_gemm_replay.py',
         't17_hc_gemm_execute.py', 't17_gemm_runner.py', 't17_gemm_launch.py', 't17_gemm_stage.py',
         't17_gemm_monitor.py', 't17_gemm_read.py')
files = {name: (HERE / name).read_bytes() for name in names}
for name in ('test_t17_hc_gemm_replay.py', 'test_t17_hc_gemm_execute.py', 'test_t17_d14_gpu.py'):
    files['tests/' + name] = (HERE / 'tests' / name).read_bytes()
identity = hashlib.sha256(b''.join(name.encode() + files[name] for name in sorted(files))).hexdigest()
stage = '/data2/FreeToken/runs/dev_D14/gemm_' + identity[:12]
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(exist_ok=False)
for name,value in data['files'].items():
 path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as stream:stream.write(base64.b64decode(value))
env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4',
 'PYTHONPATH':'/data2/FreeToken/wt/e2d14/python:/data2/FreeToken/wt/e2d14'}
steps={}
try:
 for name,argv in [('replay_tests',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'tests/test_t17_hc_gemm_replay.py'),str(stage/'tests/test_t17_hc_gemm_execute.py')]),
  ('gate_tests',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'tests/test_t17_d14_gpu.py')]),
  ('compile',[sys.executable,'-c',"import pathlib,runpy; [compile(p.read_bytes(),str(p),'exec') for p in pathlib.Path.cwd().rglob('*.py')]; [compile(runpy.run_path(name)['PROGRAM'],name+' embedded','exec') for name in ('t17_gemm_monitor.py','t17_gemm_read.py')]; print('COMPILE_PASS')"]),
  ('preparation',[sys.executable,str(stage/'t17_gemm_runner.py'),'--cpu-preparation-probe'])]:
  process=subprocess.run(argv,cwd=stage,env=env,capture_output=True,timeout=120)
  log=stage/(name+'.log');log.write_bytes(process.stdout+process.stderr)
  if process.returncode:
   print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
  steps[name]={'returncode':process.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 proof=json.loads((stage/'preparation.log').read_text().splitlines()[-1])
 if proof.get('gpu_started') is not False or proof.get('schema')!='ft_t17_gemm_preparation/v1' or proof['plan']['operator']!='gdn':
  raise ValueError('real CPU-only GDN preparation required')
 with (stage/'plan.json').open('x') as stream:stream.write(json.dumps(proof['plan'],indent=2)+'\n')
 source_names=tuple(data['files'])+('plan.json',)
 report={'schema':'ft_t17_gemm_cpu/v1','gpu_started':False,'steps':steps,'preparation':proof,
  'source_files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in source_names},
  'diagnostic_only':True,'R023_verdict':'not_met'}
 (stage/'cpu_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'stage':str(stage),'report_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest(),
  'report':report,'tests':(stage/'replay_tests.log').read_text().strip().splitlines()[-1]}))
finally:
 for path in reversed([stage,*stage.rglob('*')]):path.chmod(path.stat().st_mode&~0o222)
'''
process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '9', '/data2/FreeToken/venv/bin/python', '-'],
                         input=('import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps({'stage': stage, 'files': {name: base64.b64encode(value).decode() for name, value in files.items()}}))+')\n'+PROGRAM).encode(),
                         capture_output=True)
if process.returncode:
    print('Retained stage:', stage)
    print(process.stderr.decode())
    raise SystemExit(process.returncode)
receipt = json.loads(process.stdout)
with (HERE / ('t17_gemm_cpu_' + identity[:12] + '.json')).open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'stage': stage, 'report_sha256': receipt['report_sha256'],
                  'tests': receipt['tests'], 'selected_operator': receipt['report']['preparation']['plan']['operator']}, indent=2))
