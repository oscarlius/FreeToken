"""Executable, fail-closed bd57 lifecycle runner for D09 reapplication.

--filedry uses the same Runner/Effects materialization path with only Popen,
HTTP, and GPU-idle callbacks replaced. --run accepts only a new root admission;
without it no process, listener, request, or lock can be created.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

HERE=Path(__file__).resolve().parent; ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/d09-page-conservation-20261010'
CANDIDATE='bd57cfdccc2a935d46cb0a89b8b36be7a18706de'; T16='E2-D09-T16-reapply-bd57-20261010'; T17='E2-D09-T17-reapply-bd57-20261010'
STARTUP=HERE/'bd57_t17_startup.py'; EXACT=HERE/'bd57_t17_exact_ids.py'; OBSERVE=HERE/'bd57_t17_observe.py'; T16_REFERENCE=HERE/'bd57_reference_t16_runner.py'; T17_REFERENCE=HERE/'bd57_reference_t17_runner.py'; T17_INPUTS=HERE/'D09_T17_EXACT_INPUTS.json'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as f: json.dump(obj,f,sort_keys=True,indent=2);f.write('\n')
def require_candidate():
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 if head!=CANDIDATE or dirty: raise RuntimeError('bd57 candidate identity/cleanliness differs')
 for name in ('_cpu_moe.cpython-310-x86_64-linux-gnu.so','_pinned_tensor.cpython-310-x86_64-linux-gnu.so'):
  p=WT/'python/freetoken/kernel'/name
  if not p.is_symlink() or not p.resolve().is_file(): raise RuntimeError('bd57 native link missing: '+name)
 return {'candidate':head,'native_links':{x.name:{'resolved':str(x.resolve()),'sha256':sha(x)} for x in (WT/'python/freetoken/kernel').glob('*.so')}}
def require_t16(closure):
 required={'rid':T16,'candidate_commit':CANDIDATE,'verdict':'kept','services':8,'calls':100}
 if not closure or any(closure.get(k)!=v for k,v in required.items()): raise RuntimeError('T17 requires a fresh sealed bd57 T16 kept closure')
def plan(stage, closure=None):
 if stage=='t16': return {'rid':T16,'stage':'T16','services':8,'calls':100,'flags':[],'server_args':{'message_boundary_ckpt':False},'input_binding':{'reference':str(T16_REFERENCE),'sha256':sha(T16_REFERENCE),'frozen_protocol':'original T16 8-service/100-call'}}
 if stage=='t17':
  require_t16(closure);return {'rid':T17,'stage':'T17','services':6,'calls':8,'flags':['--enable-message-boundary-ckpt'],'server_args':{'message_boundary_ckpt':True},'cells':[{'P':20282,'tail':1020},{'P':22558,'tail':197}],'input_binding':{'reference':str(T17_REFERENCE),'reference_sha256':sha(T17_REFERENCE),'inputs':str(T17_INPUTS),'inputs_sha256':sha(T17_INPUTS)}}
 raise ValueError(stage)
@dataclass
class Effects:
 root: Path
 idle_callback: callable | None = None
 def materialize(self,item,index):
  arm=self.root/'services'/f"{item['stage'].lower()}_{index:02d}";arm.mkdir(parents=True)
  for src,dst in ((STARTUP,'t17_d14_startup.py'),(EXACT,'t17_d14_exact_ids.py'),(OBSERVE,'t17_d14_observe.py')): shutil.copyfile(src,arm/dst)
  argv=[str(ROOT/'venv/bin/python'),'-u',str(arm/'t17_d14_startup.py'),'serve','--host','127.0.0.1','--port',str(33000+index),'--model-path',str(ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'),'--enable-special-token-ckpt']+item['flags']
  binding={'arm':str(arm),'cwd':str(arm),'pythonpath':str(WT/'python'),'argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),'input_binding':{'rid':item['rid'],'candidate':CANDIDATE,'stage':item['stage'],'service':index,'calls':item['calls'],'server_args':item['server_args']}}
  if item['stage']=='T16' and '--enable-message-boundary-ckpt' in argv: raise RuntimeError('T16 enabled message-boundary flag')
  return binding
 def spawn(self,binding):
  env=os.environ|{'PYTHONPATH':binding['pythonpath'],'FT_DEV_STATE_DUMP':str(Path(binding['arm'])/'state_dump'),'CUDA_VISIBLE_DEVICES':'0'}
  return subprocess.Popen(binding['argv'],cwd=binding['cwd'],env=env,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 def ready(self,proc,binding):
  opener=build_opener(ProxyHandler({}));end=time.monotonic()+1800;url='http://127.0.0.1:'+str(binding['argv'][binding['argv'].index('--port')+1])
  while time.monotonic()<end:
   if proc.poll() is not None:raise RuntimeError('service exited before ready')
   try:
    with opener.open(url+'/health',timeout=10) as r:
     if json.loads(r.read()).get('status')=='ok':return url
   except OSError: time.sleep(1)
  raise RuntimeError('readiness timeout')
 def request(self,url,item):
  # Actual execution obtains frozen inputs from the admission, never this CPU packet.
  raise RuntimeError('no frozen input binding installed')
 def wait_gpu_idle(self,deadline):
  while time.monotonic() < deadline:
   if self.idle_callback is not None:
    if self.idle_callback(): return
   else:
    result=subprocess.run(['/usr/bin/nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=10)
    if result.returncode == 0 and not result.stdout.strip(): return
   time.sleep(1)
  raise RuntimeError('failed_harness GPU idle wait expired')
 def cleanup(self,proc,deadline):
  proc.terminate();proc.wait(timeout=max(1,deadline-time.monotonic()))
  self.wait_gpu_idle(deadline)
class FileDryEffects(Effects):
 def __init__(self,root): super().__init__(root,idle_callback=lambda:True)
 def spawn(self,binding): return object()
 def ready(self,proc,binding): return 'cpu://no-listener'
 def request(self,url,item): return {'cpu_fake':True}
 def cleanup(self,proc,deadline):
  if time.monotonic()>deadline: raise RuntimeError('failed_harness cleanup deadline expired')
def execute(item,effects):
 bindings=[]
 for index in range(item['services']):
  binding=effects.materialize(item,index);proc=effects.spawn(binding)
  try:
   url=effects.ready(proc,binding)
   for _ in range((item['calls']//item['services']) + (1 if index < item['calls'] % item['services'] else 0)): effects.request(url,item)
  finally: effects.cleanup(proc,time.monotonic()+120)
  bindings.append(binding)
 return bindings
def admission(path, stage):
 d=json.loads(Path(path).read_text())
 if d.get('root_approved') is not True or d.get('candidate')!=CANDIDATE or d.get('stage')!=stage: raise RuntimeError('new bd57 root admission rejects execution')
 if stage=='t17': require_t16(d.get('t16_closure'))
 return d
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--stage',choices=('t16','t17'),required=True);p.add_argument('--admission',type=Path);a=p.parse_args()
 if a.filedry==a.run: p.error('choose exactly one of --filedry or --run')
 require_candidate()
 if a.filedry:
  if a.stage=='t17':
   try: plan('t17')
   except RuntimeError as e: print(json.dumps({'status':'pre_gpu_failed','reason':str(e),'effects':[]}));return
  item=plan('t16');root=HERE/'cpu_filedry_runtime';shutil.rmtree(root,ignore_errors=True);root.mkdir();bindings=execute(item,FileDryEffects(root));print(json.dumps({'status':'cpu_filedry_complete','plan':item,'bindings':bindings,'effects':'same Runner/Effects; only Popen/HTTP/GPU callbacks faked'}));return
 d=admission(a.admission,a.stage);item=plan(a.stage,d.get('t16_closure'));root=Path(d['runroot'])/item['rid'];root.mkdir(parents=True,exist_ok=False);put(root/'input_binding.json',{'plan':item,'admission_sha256':sha(a.admission)});execute(item,Effects(root));put(root/'terminal.json',{'proposed_verdict':'pending_independent_review'})
if __name__=='__main__': main()


