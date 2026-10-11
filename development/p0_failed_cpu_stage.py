"""Test exact failed-archive closer and replay seven real failures on private copies."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ['scripts/round_json_append.py','scripts/round_close.py',
    'scripts/tests/test_round_json_append.py','scripts/tests/test_round_close.py',
    'development/p0_failed_harness_close.py',
    'development/tests/test_p0_failed_harness_close.py','development/p0_failed_cpu_stage.py']
files = {name:(ROOT/name).read_bytes() for name in FILES}
identity = hashlib.sha256(b''.join(name.encode()+files[name] for name in FILES)).hexdigest()
stage = '/data2/FreeToken/runs/dev_D04/failed_archive_' + identity[:12]
program = r'''
import base64,hashlib,importlib.util,json,os,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(parents=True,exist_ok=False)
for relative,encoded in data['files'].items():
 p=stage/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
run=subprocess.run(['/data2/FreeToken/venv/bin/python','-m','pytest','-q','scripts/tests/test_round_json_append.py','scripts/tests/test_round_close.py','development/tests/test_p0_failed_harness_close.py'],cwd=stage,env=env,capture_output=True)
(stage/'pytest.log').write_bytes(run.stdout+run.stderr)
assert run.returncode==0,run.stderr.decode()
sys.path.insert(0,str(stage/'scripts'))
import round_close as closer,round_json_append as writer
spec=importlib.util.spec_from_file_location('failed_prepare',stage/'development/p0_failed_harness_close.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
canonical=pathlib.Path('/data2/_shared/runs/ft_rounds');source=pathlib.Path('/data2/FreeToken/runs/plan_batches')
private=stage/'private_real_failures';private.mkdir();results=[]
for rid in helper.ROUND_IDS:
 prepared=helper.copy_checked(canonical/rid,private,source)
 assert not any(x['pid_terminated_now'] is False for x in prepared['plan']['arms'])
 target=prepared['target']
 closed=helper.close_one(prepared,stage/'scripts/round_close.py',stage/'scripts/round_json_append.py')
 assert closed['closed'] is True
 manifest=helper.sha256(target/'MANIFEST.sha256')
 _,current,versions=writer.validate_history(target/'round.json',target/'round_history')
 assert current['verdict']=='failed_harness' and len(versions)==2
 assert all(helper.sha256(pathlib.Path(p))==h for p,h in prepared['source_artifact_hashes'].items())
 if rid=='E2-R012':assert not (target/'B1/serve_args.txt').exists()
 results.append({'round_id':rid,'closed':closed['closed'],'close_result':closed,'manifest_sha256':manifest,'round_json_sha256':helper.sha256(target/'round.json'),
  'source_sha256_pre_and_post_equal':True,'missing_args_preserved':not (target/'B1/serve_args.txt').exists() if rid=='E2-R012' else None})
report={'schema':'ft_failed_archive_cpu_replay/v1','stage':str(stage),'gpu_started':False,'canonical_rounds_mutated':False,
 'pytest_returncode':run.returncode,'pytest_output':run.stdout.decode().strip(),'rounds':results,
 'files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in data['files']},
 'pytest_log_sha256':hashlib.sha256((stage/'pytest.log').read_bytes()).hexdigest()}
(stage/'report.json').write_text(json.dumps(report,indent=2)+'\n')
for p in reversed([stage,*sorted(stage.rglob('*'))]):p.chmod(p.stat().st_mode&~0o222)
print(json.dumps(report))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
    '/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
    input=json.dumps({'stage':stage,'files':{k:base64.b64encode(v).decode() for k,v in files.items()}}).encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode(errors='replace'))
    raise SystemExit(result.returncode)
report=json.loads(result.stdout)
(ROOT/'development/p0_failed_archive_cpu_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
