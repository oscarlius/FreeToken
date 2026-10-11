"""One-service D10 prototype parent; root admission is required for --run."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, socket, subprocess, sys, time
from urllib.request import ProxyHandler, build_opener
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=Path('/data2/FreeToken'); RID='E2-D10-T16-night-20261010'; CAND='22ff3a389eae3724cdca9a45f2e19577082a2032'

def load(name):
 s=importlib.util.spec_from_file_location(name,HERE/name);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def reserve_pair():
 held=[]
 try:
  for _ in range(2):
   s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',0));held.append(s)
  return held
 except BaseException:
  for s in held:s.close()
  raise
def release(held):
 for s in held:s.close()
def admission(path):
 a=load('d10_aiperf_runner_v4.py');return a.require_admission(path)
def controller(admission_path,deps=None):
 """Allocate one D07 batch and publish an immutable child binding."""
 if deps:return deps.reserve(admission_path)
 g=load('d07_g3g4_prepare.py');admission(admission_path)
 if g.LOCK.exists() or g.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists')
 life=g.load_owned_lifecycle();h=life.verified_module(ROOT/'runs/plan_batches/e2_launch.py',g.ATOMIC_HELPER_SHA,'d10_proto_atomic');b=h.next_batch(g.ROUNDS);receipt=ROOT/'runs/dev_D10'/f'prototype_{RID}_{b}.json';receipt.parent.mkdir(parents=True,exist_ok=True)
 argv=[sys.executable,str(Path(__file__).resolve()),'--run','--owned-child','--admission',str(admission_path),'--batch',str(b),'--receipt',str(receipt)]
 got=life.reserve_process(h,b,RID,argv,receipt,{'schema':'ft_d10_prototype_launch/v1','state':'reserved','rid':RID,'batch':b,'candidate':CAND,'argv_sha256':g.argv_sha256(argv),'controller':g.process_birth(),'budget':{'services':1,'calls':8}})
 return g.publish_child_binding(receipt,got,g.process_identity(got['batch_pid']),lifecycle=life)
def child(admission_path,batch,receipt,deps=None):
 """The sole path that starts a service and then invokes AIPerf's eight calls."""
 if deps:return deps.child(admission_path,batch,receipt)
 g=load('d07_g3g4_prepare.py');doc=admission(admission_path);a=load('d10_aiperf_runner_v4.py'); owner=g.take_d07_gpu_lock(RID,batch);proc=None;safe=False
 try:
  required={'service_argv','service_cwd','endpoint','output'}
  if not required <= set(doc):raise RuntimeError('root-owned service argv receipt is required before prototype child execution')
  held=reserve_pair(); ports=[s.getsockname()[1] for s in held];release(held)
  argv=doc['service_argv']
  wt=ROOT/'wt/d10-staggered-v1'; args=(wt/'python/freetoken/server/args.py').read_bytes()
  if '--enable-d10-staggered-decode' not in argv or hashlib.sha256(args).hexdigest()!='203c7c850af8bdb8cc96e8280ff5a0ab2b4bef4a2623f36c0b8c8652af151a57':raise RuntimeError('D10 source or enabled argv differs')
  if not (wt/'python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so').is_file():raise RuntimeError('native reuse bytes absent')
  event=Path(doc['output'])/'d10_branch_event.json'
  proc=subprocess.Popen(argv,cwd=doc['service_cwd'],start_new_session=True,env=dict(os.environ,PYTHONPATH=str(HERE)+os.pathsep+str(wt/'python'),FT_D10_BRANCH_EVENT=str(event)))
  opener=build_opener(ProxyHandler({})); deadline=time.monotonic()+1800
  while time.monotonic()<deadline:
   if proc.poll() is not None:raise RuntimeError('prototype service exited before health')
   try:
    with opener.open(doc['endpoint'].rstrip('/')+'/health',timeout=10) as response:
     health=json.loads(response.read());
     if health.get('status')=='ok':break
   except OSError: time.sleep(2)
  else: raise TimeoutError('prototype health timeout')
  (Path(doc['output'])/'service_identity.json').write_text(json.dumps({'pid':proc.pid,'health':health,'argv_sha256':hashlib.sha256(json.dumps(argv).encode()).hexdigest()})+'\n')
  a.run(admission_path,doc['endpoint'],Path(doc['output']))
  if not event.is_file() or json.loads(event.read_text()) != {'method':'Engine._forward_d10_staggered_decode','entered':True}:raise RuntimeError('D10 decode branch proof absent')
  safe=True
 finally:
  if proc is not None:g.load_owned_lifecycle().stop_owned_process(proc,120,30)
  if proc is None or not g.load_owned_lifecycle().owned_group_alive(proc.pid):
   rebound=reserve_pair();release(rebound);g.release_d07_gpu_lock(owner)
def filedry():
 """Inject controller/child dependencies; no D07, process, HTTP, or GPU."""
 root=HERE/'evidence_prototype_controlchain_v2';assert not root.exists();root.mkdir()
 class Fake:
  def reserve(self,p):
   d={'state':'launched','rid':RID,'candidate':CAND,'batch':1,'source_sha256':sha(__file__),'admission':str(p)};(root/'receipt.json').write_text(json.dumps(d));return d
  def child(self,p,b,r):
   held=reserve_pair();ports=[x.getsockname()[1] for x in held];release(held);again=[]
   for port in ports:s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port));again.append(s)
   release(again);return {'services':1,'calls':8,'listener_rebound':True,'gpu':False,'http':False}
 f=Fake();binding=controller(root/'sealed_admission.json',f);result=child(root/'sealed_admission.json',1,root/'receipt.json',f);out=binding|result|{'controller_called':True,'child_called':True};(root/'terminal.json').write_text(json.dumps(out,sort_keys=True));return root/'terminal.json'
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--receipt',type=Path);x=p.parse_args()
 if x.filedry:print(filedry());return
 if x.run and x.owned_child and x.admission and x.batch and x.receipt:child(x.admission,x.batch,x.receipt);return
 if x.run and x.admission and not x.owned_child:controller(x.admission);return
 p.error('select --filedry or guarded --run')
if __name__=='__main__':main()
