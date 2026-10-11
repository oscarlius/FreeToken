"""Create and CPU-validate an immutable content-addressed shared T16 stage."""
import base64,hashlib,json,shlex,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
NAMES=('t16_candidate_runner_full_tail.py','t16_full_tail_base_runner.py','t16_process_lifecycle.py','t16_candidate_launch_shared.py','t16_candidate_stage_shared.py','t16_candidate_runner.py','t16_candidate_runner_d07.py','t16_candidate_launch.py','t16_candidate_launch_d07.py','t16_candidate_launch_full_tail.py','tests/test_t16_full_tail.py','tests/test_t16_candidate_runner_full_tail.py','tests/test_t16_shared_prefill.py','tests/fixtures/t16_failed_full_tail.json','tests/test_t16_future_entrypoints.py','tests/test_t16_process_lifecycle.py','tests/test_t16_candidate_launch_shared.py')
TESTS=('tests/test_t16_full_tail.py','tests/test_t16_candidate_runner_full_tail.py','tests/test_t16_shared_prefill.py','tests/test_t16_future_entrypoints.py','tests/test_t16_process_lifecycle.py','tests/test_t16_candidate_launch_shared.py')
def source_manifest(root=None):
 root=Path(root) if root is not None else HERE
 files={n:(root/n).read_bytes() for n in NAMES}
 legacy=root/'t16_legacy_base_runner.py'
 if not legacy.is_file():legacy=root.parent/'plan/01_测试与调研/batches/t16_runner.py'
 files['t16_legacy_base_runner.py']=legacy.read_bytes()
 return hashlib.sha256(b''.join(n.encode()+files[n] for n in sorted(files))).hexdigest(),files
def stage():
 identity,files=source_manifest();target='/data2/FreeToken/runs/dev_D14/shared_t16_'+identity[:12]
 payload={'target':target,'files':{n:base64.b64encode(v).decode() for n,v in files.items()},'tests':TESTS}
 program="""import base64,hashlib,json,os,pathlib,re,subprocess,sys
d=json.load(sys.stdin);p=pathlib.Path(d['target']);p.mkdir(parents=True,exist_ok=False)
for n,v in d['files'].items():
 q=p/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(base64.b64decode(v))
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
tests=d['tests']
r=subprocess.run(['/data2/FreeToken/venv/bin/python','-m','pytest','-q','-p','no:cacheprovider',*tests],cwd=p,env=env,text=True,capture_output=True,timeout=180)
(p/'cpu_validation.log').write_text(r.stdout+r.stderr)
if r.returncode:
 print(r.stdout+r.stderr,file=sys.stderr)
 raise SystemExit(r.returncode)
matches=re.findall(r'(\\d+) passed',r.stdout)
if len(matches)!=1 or int(matches[0])<48 or re.search(r'\\d+ (failed|skipped|error)',r.stdout):raise ValueError('incomplete successful Linux regression')
receipt={'schema':'ft_t16_shared_cpu_stage/v1','gpu_started':False,'status':'passed','passed':int(matches[0]),'tests':tests,'files':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in d['files']},'log_sha256':hashlib.sha256((p/'cpu_validation.log').read_bytes()).hexdigest(),'test_output':r.stdout}
with (p/'cpu_validation.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\\n')
for q in sorted(p.rglob('*'),reverse=True): q.chmod(0o444 if q.is_file() else 0o555)
p.chmod(0o555);print(json.dumps({'stage':str(p),'receipt_sha256':hashlib.sha256((p/'cpu_validation.json').read_bytes()).hexdigest()}))"""
 r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9','/data2/FreeToken/venv/bin/python','-c',shlex.quote(program)],input=json.dumps(payload),text=True,capture_output=True)
 if r.returncode: raise RuntimeError('retained failed CPU stage: '+target+'\n'+r.stderr+r.stdout)
 receipt=json.loads(r.stdout)
 with (HERE/('t16_shared_stage_'+identity[:12]+'.json')).open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
 return receipt
if __name__=='__main__':print(json.dumps(stage()))
