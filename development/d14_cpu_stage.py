"""Run D14 CPU regressions on exact baseline and LF candidate bytes on the host."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT/'development/e2d14'
NAMES = ['python/freetoken/attention/linear.py','python/freetoken/engine/engine.py',
    'python/freetoken/models/qwen4_exp/model.py','tests/engine/test_layer_major_tracks.py']
files = {name:(TREE/name).read_bytes().replace(b'\r\n',b'\n') for name in NAMES}
identity = hashlib.sha256(b''.join(name.encode()+files[name] for name in NAMES)).hexdigest()
stage = '/data2/FreeToken/runs/dev_D14/cpu_' + identity[:12]
program = r'''
import base64,hashlib,io,json,os,pathlib,subprocess,sys,tarfile
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);stage.mkdir(parents=True,exist_ok=False)
repo=pathlib.Path('/data2/FreeToken/wt/e2base');commit='23f2e2caa3395837c9474735ffc83321f3b9b5a1'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==commit
archive=subprocess.check_output(['git','-C',str(repo),'archive',commit])
for kind in ('baseline','candidate'):
 tree=stage/kind;tree.mkdir()
 with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
  for member in tar.getmembers():
   p=pathlib.PurePosixPath(member.name)
   if p.is_absolute() or '..' in p.parts or not (member.isfile() or member.isdir()):raise ValueError('unsafe source archive member')
  tar.extractall(tree)
 for relative in ['python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so','python/freetoken/kernel/_pinned_tensor.cpython-310-x86_64-linux-gnu.so']:
  source=repo/relative
  if source.exists():(tree/relative).symlink_to(source)
 test='tests/engine/test_layer_major_tracks.py'
 (tree/test).write_bytes(base64.b64decode(data['files'][test]))
 if kind=='candidate':
  for name,encoded in data['files'].items():(tree/name).write_bytes(base64.b64decode(encoded))
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false')
entry="import sys,pathlib;tree=pathlib.Path(sys.argv[1]);sys.path[:0]=[str(tree/'python'),str(tree),'/data2/FreeToken/venv/lib/python3.10/site-packages'];import freetoken,torch;assert freetoken.__file__==str(tree/'python/freetoken/__init__.py');import pytest;rc=pytest.main(['-q','-p','no:cacheprovider','tests/engine/test_layer_major_tracks.py']);assert not torch.cuda.is_initialized();raise SystemExit(rc)"
steps=[]
for kind in ('baseline','candidate'):
 tree=stage/kind
 completed=subprocess.run(['/data2/FreeToken/venv/bin/python','-S','-c',entry,str(tree)],cwd=tree,env=env,capture_output=True,timeout=180)
 log=completed.stdout+completed.stderr;(stage/(kind+'.log')).write_bytes(log)
 steps.append({'kind':kind,'returncode':completed.returncode,'log_sha256':hashlib.sha256(log).hexdigest(),'output':log.decode(errors='replace')[-6000:]})
report={'schema':'ft_d14_cpu_before_after/v1','stage':str(stage),'baseline_commit':commit,'candidate_committed':False,'gpu_started':False,
 'files':{name:hashlib.sha256(base64.b64decode(encoded)).hexdigest() for name,encoded in data['files'].items()},'steps':steps}
(stage/'report.json').write_text(json.dumps(report,indent=2)+'\n')
for p in reversed([stage,*sorted(stage.rglob('*'))]):
 if not p.is_symlink():p.chmod(p.stat().st_mode&~0o222)
print(json.dumps(report))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
    '/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],
    input=json.dumps({'stage':stage,'files':{k:base64.b64encode(v).decode() for k,v in files.items()}}).encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode(errors='replace'))
    raise SystemExit(result.returncode)
report=json.loads(result.stdout)
(ROOT/'development/d14_cpu_before_after.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
