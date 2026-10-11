"""Freeze and validate the v2 continuation CPU surface on the Linux owner host."""
from __future__ import annotations
import base64, hashlib, json, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
RUNTIME=HERE/'t17_continuation_runtime_v2.py'

def sha(b): return hashlib.sha256(b).hexdigest()
def main():
 runtime={"candidate":"2396728f5f210b98bfde0b8ba3556e9cbc2b234f"}
 files={}
 required=[]
 ns={};exec(RUNTIME.read_text(),ns); required=list(ns['REQUIRED_SOURCE_FILES'])
 for name in required:
  path=HERE/name
  assert path.is_file() and not path.is_symlink(), name
  files['development/'+name]=path.read_bytes()
 source=HERE/'e2d16-readers'
 for path in (source/'scripts/equiv_suite').glob('*.py'):
  files['scripts/equiv_suite/'+path.name]=path.read_bytes()
  files['development/equiv_suite/'+path.name]=path.read_bytes()
 suite_tests=[f'tests/scripts/test_equiv_{name}.py' for name in ('suite','continuation','path_readers','retained_d03','sampler_capture','retained_state','service_capture')]
 for name in suite_tests+['tests/conftest.py']:files[name]=(source/name).read_bytes()
 name='t17_continuation_inputs_cpu_fd6362813705.json'
 files['development/'+name]=(HERE/name).read_bytes()
 files['d03_tools/logits_probe.py']=(HERE/'e2d03/scripts/logits_probe.py').read_bytes()
 files['stage_source.py']=Path(__file__).read_bytes()
 for name in ('tests/test_t17_continuation_selection.py','tests/test_t17_continuation_runner_v2.py'):
  files[name]=(ROOT/name).read_bytes()
 digest=sha(b''.join(k.encode()+files[k] for k in sorted(files)))
 stage=f'/data2/FreeToken/runs/dev_D16/v2_cpu_{digest[:12]}'
 payload={'stage':stage,'files':{k:base64.b64encode(v).decode() for k,v in files.items()},'candidate':runtime['candidate'],'tests':suite_tests+['tests/test_t17_continuation_selection.py','tests/test_t17_continuation_runner_v2.py']}
 program=r'''import base64,hashlib,json,os,pathlib,re,subprocess,sys
x=json.load(sys.stdin); s=pathlib.Path(x['stage']); s.mkdir(parents=True,exist_ok=False)
def w(n,b):
 p=s/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(b))
def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for n,b in x['files'].items():w(n,b)
sys.path.insert(0,str(s/'development'))
import t17_d14_runner as startup_helper
startup_helper.freeze_startup_wrapper(s/'development')
env={k:v for k,v in os.environ.items() if k!="PYTHONPATH" and not k.startswith("FT_")};env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(s/'development')+':'+str(s/'scripts')+':/data2/FreeToken/wt/e2base1/python',FT_D16_D03_TOOL=str(s/'d03_tools/logits_probe.py'))
cmd=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*x['tests']];p=subprocess.run(cmd,cwd=s,env=env,capture_output=True,text=True);(s/'pytest.log').write_text(p.stdout+p.stderr)
probe=[sys.executable,'-c',"import json,pathlib,torch,freetoken,t17_continuation_runner_v2,t17_continuation_runtime_v2; p=pathlib.Path(freetoken.__file__).resolve(); assert p.is_relative_to(pathlib.Path('/data2/FreeToken/wt/e2base1/python')); assert not torch.cuda.is_initialized(); print(json.dumps({'origin':str(p),'cuda_initialized':False}))"];imp=subprocess.run(probe,cwd=s/'development',env=env,capture_output=True,text=True);(s/'import.log').write_text(imp.stdout+imp.stderr)
tree='/data2/FreeToken/wt/e2base1'
head=subprocess.check_output(['git','-C',tree,'rev-parse','HEAD'],text=True).strip()
clean=not subprocess.check_output(['git','-C',tree,'status','--porcelain'],text=True).strip()
assert head==x['candidate'] and clean
counts=re.findall(r'(\d+) passed',p.stdout)
passed=int(counts[0]) if len(counts)==1 else None
r={'runtime_lifecycle_verified':False,'admitted':False,'candidate_commit':head,'clean':clean,'verdict':'PASS' if p.returncode==0 and imp.returncode==0 and passed==100 and not re.search(r'\d+ (failed|skipped|error)',p.stdout) else 'FAIL','schema':'ft_t17_v2_cpu_freeze/v2','candidate':x['candidate'],'argv':cmd,'pytest_returncode':p.returncode,'pytest_log_sha256':sh(s/'pytest.log'),'binding_argv':probe,'passed':passed,'import_returncode':imp.returncode,'import_log_sha256':sh(s/'import.log'),'gpu_started':False,'requests_sent':False,'files':{q.relative_to(s).as_posix():sh(q) for q in s.rglob('*') if q.is_file()}}
(s/'report.json').write_text(json.dumps(r,indent=2)+'\n');
for q in sorted(s.rglob('*'),reverse=True):q.chmod(0o444 if q.is_file() else 0o555)
s.chmod(0o555);print(json.dumps({'stage':str(s),'report_sha256':sh(s/'report.json'),'verdict':r['verdict'],'passed':r['passed']}));sys.exit(0 if r['verdict']=='PASS' else 1)'''
 wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+program
 result=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],input=wire,text=True,capture_output=True)
 (HERE/f't17_v2_cpu_{digest[:12]}.json').write_text(json.dumps({'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2))
 print(result.stdout[-2500:]);print(result.stderr)
 if result.returncode: raise SystemExit(result.returncode)
if __name__=='__main__':main()
