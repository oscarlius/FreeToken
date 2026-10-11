"""Stage exact D04/batch bytes and replay on private copies of real sealed rounds."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ['scripts/round_json_append.py','scripts/round_close.py',
    'scripts/tests/test_round_json_append.py','scripts/tests/test_round_close.py',
    'development/p0_verdict_batch.py','development/p0_verdict_proposal.json']
payload = {name:base64.b64encode((ROOT/name).read_bytes()).decode() for name in FILES}
batch_sha = hashlib.sha256((ROOT/'development/p0_verdict_batch.py').read_bytes()).hexdigest()
stage = '/data2/FreeToken/runs/dev_D04/p0_verdict_' + batch_sha[:8]
program = r'''
import base64,hashlib,importlib.util,json,os,pathlib,shutil,subprocess,sys,tempfile
data=json.load(sys.stdin); stage=pathlib.Path(data['stage']); stage.mkdir(parents=True,exist_ok=False)
for relative,encoded in data['files'].items():
 p=stage/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(encoded))
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false')
py='/data2/FreeToken/venv/bin/python'
tested=subprocess.run([py,'-m','pytest','-q','scripts/tests/test_round_json_append.py','scripts/tests/test_round_close.py'],cwd=stage,env=env,capture_output=True)
(stage/'pytest.log').write_bytes(tested.stdout+tested.stderr)
if tested.returncode:raise SystemExit('D04 Linux tests failed')
spec=importlib.util.spec_from_file_location('p0_verdict_batch',stage/'development/p0_verdict_batch.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
writer=b.load_writer(stage/'scripts/round_json_append.py');proposal=json.loads((stage/'development/p0_verdict_proposal.json').read_text())
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
readonly=b.execute(writer,root,proposal,stage/'preflight.json',False)
private=stage/'private_real_rounds';private.mkdir()
for item in [*proposal['kept_measurements'],proposal['separate_r020_d06']]:
 src=root/item['round_id'];dst=private/item['round_id'];dst.mkdir()
 for name in ['round.json','MANIFEST.sha256',*item['evidence_paths']]:
  target=dst/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src/name,target)
 shutil.copytree(src/'round_history',dst/'round_history')
 for p in [dst,*dst.rglob('*')]:p.chmod(p.stat().st_mode&~0o222)
applied=b.execute(writer,private,proposal,stage/'private_replay.json',True)
report={'schema':'ft_p0_verdict_cpu_replay/v1','stage':str(stage),'gpu_started':False,'canonical_rounds_mutated':False,
 'linux_pytest_returncode':tested.returncode,'linux_pytest_output':tested.stdout.decode().strip(),
 'preflight_rounds':readonly['all_rounds_preflighted'],'private_real_rounds_appended':len(applied['rounds']),
 'files':{name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in data['files']},
 'preflight_sha256':b.sha(stage/'preflight.json'),'private_replay_sha256':b.sha(stage/'private_replay.json'),
 'pytest_log_sha256':b.sha(stage/'pytest.log')}
(stage/'cpu_report.json').write_text(json.dumps(report,indent=2)+'\n')
for p in reversed([stage,*sorted(stage.rglob('*'))]):p.chmod(p.stat().st_mode&~0o222)
print(json.dumps(report))
'''
result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
    '/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
    input=json.dumps({'stage':stage,'files':payload}).encode(), capture_output=True)
if result.returncode:
    print(result.stderr.decode(errors='replace'))
    raise SystemExit(result.returncode)
report = json.loads(result.stdout)
(ROOT/'development/p0_verdict_cpu_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
