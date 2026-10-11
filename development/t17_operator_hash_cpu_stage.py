"""Freeze observer parity tests and byte-identical CPU benchmark on host9."""
import base64,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
PROGRAM=r'''import base64,hashlib,json,os,pathlib,subprocess,sys,time
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(exist_ok=False)
for name,data in x['files'].items():
 p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(stage))
argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t17_operator_observe.py']
result=subprocess.run(argv,cwd=stage,env=env,capture_output=True,text=True)
(stage/'pytest.log').write_text(result.stdout+result.stderr)
sys.path.insert(0,str(stage));os.environ['CUDA_VISIBLE_DEVICES']='';import torch,t17_operator_observe as obs
assert not torch.cuda.is_initialized()
bench=[]
for dtype in [torch.float32,torch.bfloat16]:
 tensor=torch.arange(4096*512,dtype=torch.float32).reshape(4096,512).to(dtype);rows=list(range(4096))
 legacy=lambda:[obs._sha(obs._bytes(tensor[i])) for i in rows]
 bulk=lambda:obs._row_hashes(tensor,rows)
 expected=legacy();assert bulk()==expected
 samples={}
 for name,fn in [('legacy',legacy),('bulk',bulk)]:
  ts=[]
  for unused in range(3):
   before=time.perf_counter();actual=fn();ts.append(time.perf_counter()-before);assert actual==expected
  samples[name]=min(ts)
 bench.append({'dtype':str(dtype),'shape':list(tensor.shape),'rows':len(rows),'byte_hashes_equal':True,'legacy_seconds':samples['legacy'],'bulk_seconds':samples['bulk'],'speedup':samples['legacy']/samples['bulk']})
assert not torch.cuda.is_initialized()
(stage/'benchmark.json').write_text(json.dumps(bench,indent=2)+'\n')
report={'schema':'ft_t17_operator_hash_cpu/v1','verdict':'PASS' if result.returncode==0 and '18 passed' in result.stdout and 'skipped' not in result.stdout else 'FAIL','argv':argv,'returncode':result.returncode,'benchmark':bench,'gpu_started':False,'requests_sent':False,'model_admitted':False,'runtime_lifecycle_verified':False,'files':{p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file()}}
(stage/'cpu_validation.json').write_text(json.dumps(report,sort_keys=True)+'\n')
for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
stage.chmod(0o555)
print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'cpu_validation.json'),'verdict':report['verdict'],'pytest':result.stdout.strip(),'benchmark':bench}))
sys.exit(0 if report['verdict']=='PASS' else 1)
'''
def main():
 files={name:(HERE/name).read_bytes() for name in ['t17_operator_observe.py','tests/test_t17_operator_observe.py']}
 files['stage_program.py']=PROGRAM.encode();files['stage_source.py']=Path(__file__).read_bytes()
 key=hashlib.sha256(b''.join(n.encode()+files[n] for n in sorted(files))).hexdigest()[:12]
 payload={'stage':'/data2/FreeToken/runs/dev_D16/operator_hash_cpu_'+key,'files':{n:base64.b64encode(b).decode() for n,b in files.items()}}
 wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
 r=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],input=wire,text=True,capture_output=True)
 with (HERE/('operator_hash_cpu_'+key+'.json')).open('x',encoding='utf-8') as f:json.dump({'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},f,indent=2)
 print(r.stdout);print(r.stderr);raise SystemExit(r.returncode)
if __name__=='__main__':main()
