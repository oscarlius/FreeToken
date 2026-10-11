"""Freeze projection diagnostic files, CPU tests and normal spawn without using GPU."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
names = ('t17_d14_gpu.py', 't17_d14_runner.py', 't17_d14_artifacts.py', 't17_d14_observe.py',
         't17_owned_launch_protocol.py', 't16_full_tail_base_runner.py', 't17_projection_runner.py',
         't17_projection_observe.py', 't17_projection_launch.py', 't17_projection_startup.py', 't17_matched_runner.py',
         't17_projection_stage.py')
files = {name: (HERE / name).read_bytes() for name in names}
files['tests/test_t17_projection_observe.py'] = (HERE / 'tests/test_t17_projection_observe.py').read_bytes()
files['tests/test_t17_projection_service.py'] = (HERE / 'tests/test_t17_projection_service.py').read_bytes()
files['tests/test_t17_projection_config.py'] = (HERE / 'tests/test_t17_projection_config.py').read_bytes()
files['tests/test_t17_d14_gpu.py'] = (HERE / 'tests/test_t17_d14_gpu.py').read_bytes()
identity = hashlib.sha256(b''.join(name.encode() + files[name] for name in sorted(files))).hexdigest()
stage = '/data2/FreeToken/runs/dev_D14/projection_' + identity[:12]
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(exist_ok=False)
for name,value in data['files'].items():
 path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as stream:stream.write(base64.b64decode(value))
prior=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R023-gate-T17')
for target,source,digest in [('t17_original_startup.py','t17_d14_startup.py','ede1ddb885b7e359838be8aad042ee84f904705aa875be48317ef2452c146b0d'),
 ('t17_d14_exact_ids.py','t17_d14_exact_ids.py','beeed7bbb48786aa336263fb69a94e464806a244bfe96cfe1c324d67b14ede89'),
 ('real_inputs.json','real_inputs.json','5f72fe7f4117dbdd1d28c1e4bf212817352db3caf43def3bd97bbf10ceeabb95')]:
 path=prior/source;payload=path.read_bytes()
 if path.is_symlink() or hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('sealed source/input differs')
 with (stage/target).open('xb') as stream:stream.write(payload)
 (stage/target).chmod(0o444)
env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4',
 'PYTHONPATH':'/data2/FreeToken/wt/e2d14/python:/data2/FreeToken/wt/e2d14','FT_LM_CHUNK':'4096',
 'FT_DEV_STATE_DUMP':str(stage/'cpu_unused_dump'),'FT_T17_OBSERVATIONS':str(stage/'cpu_observations.jsonl'),
 'FT_T17_PROJECTION':str(stage/'cpu_projection')}
steps={}
try:
 for name,argv in [('observer_tests',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'tests/test_t17_projection_observe.py'),str(stage/'tests/test_t17_projection_service.py'),str(stage/'tests/test_t17_projection_config.py')]),
  ('gate_tests',[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(stage/'tests/test_t17_d14_gpu.py')]),
  ('compile',[sys.executable,'-c',"import pathlib; [compile(p.read_bytes(),str(p),'exec') for p in pathlib.Path.cwd().rglob('*.py')]; print('COMPILE_PASS')"]),
  ('startup_spawn',[sys.executable,str(stage/'t17_projection_startup.py'),'--cpu-startup-probe'])]:
  process=subprocess.run(argv,cwd=stage,env=env,capture_output=True,timeout=120)
  log=stage/(name+'.log');log.write_bytes(process.stdout+process.stderr)
  if process.returncode:
   print((process.stdout+process.stderr).decode(),file=sys.stderr);raise SystemExit(process.returncode)
  steps[name]={'returncode':process.returncode,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 proof=json.loads((stage/'startup_spawn.log').read_text().splitlines()[-1])
 structure=proof.get('worker',{}).get('model_structure',{})
 if (structure.get('hf_ple_layer_ids')!=[2] or structure.get('parsed_ple_decoder_indices')!=[1]
  or structure.get('parser',{}).get('path')!='/data2/FreeToken/wt/e2d14/python/freetoken/models/qwen4_exp/config.py'
  or structure.get('parser',{}).get('sha256')!='72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607'):
  raise ValueError('actual candidate parser mapping proof differs')
 source_names=tuple(data['files'])+('t17_original_startup.py','t17_d14_exact_ids.py','real_inputs.json')
 report={'schema':'ft_t17_projection_cpu/v1','gpu_started':False,'steps':steps,'spawn_proof':proof,
  'source_files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in source_names},
  'diagnostic_only':True,'R023_verdict':'not_met'}
 (stage/'cpu_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'stage':str(stage),'report_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest(),
  'report':report,'tests':(stage/'observer_tests.log').read_text().strip().splitlines()[-1]}))
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
with (HERE / ('t17_projection_cpu_' + identity[:12] + '.json')).open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'stage': stage, 'report_sha256': receipt['report_sha256'],
                  'tests': receipt['tests'], 'spawn_proof': receipt['report']['spawn_proof']}, indent=2))
