"""D10 V8 prototype: canonical admissions and per-group truthful execution."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, socket, subprocess, sys, time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

HERE=Path(__file__).resolve().parent; ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/d10-cache-persistent'
ROUND_ROOT=Path('/data2/_shared/runs/ft_rounds'); RUNS=ROOT/'runs/dev_D10_cache'
RID='E2-D10-PROTOTYPE-cache-20261010'; CANDIDATE='54955f7343fe11c5c0936d18570cfbd826c0f155'; PARENT='22ff3a389eae3724cdca9a45f2e19577082a2032'; T16_RID='E2-D10-T16-night-20261010'; D09_RID='E2-D09-T16-night-20261010-retry1'; FLAG='--d10-staggered-decode'; MAX_CALLS=8
NATIVE=HERE/'d10_native_provenance_v2.json'; REUSE=HERE/'ROOT_NATIVE_REUSE_V2.json'
ACTUAL=('d10_cache_owned_parent.py','d10_aiperf_runner_v8.py','d10_aiperf_parse_v7.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py','d07_g3g4_prepare.py','inputs_r045_v7.jsonl','inputs_ignore_eos256_v7.jsonl')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def runner(): return load(HERE/'d10_aiperf_runner_v8.py','d10v8runner')
def d07():
 m=load(HERE/'d07_g3g4_prepare.py','d10v8d07');m.CANDIDATE=CANDIDATE;m.RID=RID;return m
def put(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as h: json.dump(x,h,sort_keys=True,indent=2);h.write('\n')
def append(p,x):
 with p.open('a',encoding='utf-8') as h:h.write(json.dumps(x,sort_keys=True)+'\n')
def hashes(): return {n:sha(HERE/n) for n in ACTUAL}
def sealed(p):
 p=Path(p)
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222:raise RuntimeError('sealed file required: '+str(p))
 return p
def reserve_pair(port):
 held=[]
 try:
  for p in (port,port+1):
   s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',p));held.append(s)
  return held
 except BaseException:
  for s in held:s.close()
  raise
def close_pair(x):
 for s in x:s.close()
def canonical(path,root):
 p=Path(path)
 if not p.is_absolute() or root not in (p,*p.parents):raise RuntimeError('noncanonical evidence path')
 return p
def manifest(directory,manifest_path):
 p=sealed(manifest_path);directory=canonical(directory,ROUND_ROOT)
 if p != directory/'MANIFEST.sha256':raise RuntimeError('manifest canonical path differs')
 rows=[]
 for line in p.read_text().splitlines():
  bits=line.split(maxsplit=1)
  if len(bits)!=2 or len(bits[0])!=64:raise RuntimeError('manifest entry malformed')
  name=bits[1].lstrip('* '); f=directory/name
  if Path(name).is_absolute() or '..' in Path(name).parts or not sealed(f) or sha(f)!=bits[0]:raise RuntimeError('manifest entry hash differs')
  rows.append(name)
 actual=sorted(str(x.relative_to(directory)) for x in directory.rglob('*') if x.is_file() and x.name!='MANIFEST.sha256')
 if sorted(rows)!=actual or len(rows)!=len(set(rows)):raise RuntimeError('manifest does not cover all entries')
 return sha(p)
def history(directory):
 h=directory/'round_history'/'SHA256SUMS';sealed(h);names=[]
 for line in h.read_text().splitlines():
  a,b=line.split(maxsplit=1); f=directory/'round_history'/b.lstrip('* ')
  if len(a)!=64 or not sealed(f) or sha(f)!=a:raise RuntimeError('round history hash differs')
  names.append(f.name)
 if not names or len(names)!=len(set(names)):raise RuntimeError('round history incomplete')
 return sha(h)
def round_binding(doc,key,rid,allowed):
 v=doc.get(key)
 if not isinstance(v,dict) or set(v)!={'round_json','round_sha256','manifest_sha256','history_sha256'}:raise RuntimeError(key+' binding shape differs')
 d=ROUND_ROOT/rid; r=sealed(v['round_json'])
 if r!=d/'round.json' or sha(r)!=v['round_sha256'] or manifest(d,d/'MANIFEST.sha256')!=v['manifest_sha256'] or history(d)!=v['history_sha256']:raise RuntimeError(key+' canonical hashes differ')
 body=json.loads(r.read_text()); verdict=body.get('verdict')
 if body.get('round_id')!=rid or verdict not in allowed:raise RuntimeError(key+' round semantics differ')
 return body
def candidate_proof():
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 diff=subprocess.check_output(['git','-C',str(WT),'diff','--name-only',PARENT,'HEAD','--','python/freetoken/kernel'],text=True)
 if head!=CANDIDATE or dirty or diff:raise RuntimeError('candidate/native source identity differs')
 paths=[ROOT/'wt/release-e2/python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so',ROOT/'wt/release-e2/python/freetoken/kernel/_pinned_tensor.cpython-310-x86_64-linux-gnu.so']
 native=[]
 for p in paths:
  if not p.is_file() or p.is_symlink():raise RuntimeError('resolved native target missing')
  native.append({'path':str(p),'sha256':sha(p),'size':p.stat().st_size})
 return {'engine_sha256':sha(WT/'python/freetoken/engine/engine.py'),'config_sha256':sha(WT/'python/freetoken/engine/config.py'),'native_target':native}
def require_admission(path):
 path=sealed(path);doc=json.loads(path.read_text());want={'schema':'ft_d10_cache_prototype_admission/v2','admit':True,'rid':RID,'candidate':CANDIDATE,'parent':PARENT,'flag':FLAG,'calls_max':8,'services_max':1,'source_sha256':hashes(),'runner_source_sha256':runner().source_hashes(),'candidate_proof':candidate_proof()}
 if any(doc.get(k)!=v for k,v in want.items()):raise RuntimeError('admission identity/source/native binding differs')
 service=doc.get('service',{});a=service.get('argv',[]);port=service.get('api_port')
 if not isinstance(port,int) or a[:2]!=['ft','serve'] or FLAG not in a or a.count('--port')!=1 or int(a[a.index('--port')+1])!=port or service.get('tcpstore_port')!=port+1 or service.get('endpoint')!=f'http://127.0.0.1:{port}' or service.get('cwd')!=str(WT) or service.get('affinity')!={'argv':['taskset','-c','1,3-47']}:raise RuntimeError('service/affinity binding differs')
 out=Path(doc.get('prototype_output',''))
 if not out.is_absolute() or out.parent!=RUNS:raise RuntimeError('output root differs')
 return doc
def child_argv(admission,batch,receipt,output):return [str(ROOT/'venv/bin/python'),str(HERE/'d10_cache_owned_parent.py'),'--run','--owned-child','--admission',str(admission),'--batch',str(batch),'--launch-receipt',str(receipt),'--worktree',str(WT),'--output-root',str(output)]
def verify_receipt(g,receipt,batch,admission,output):
 # Do not delegate WT/output validation to the custom-argv escape hatch.
 g.require_child_receipt(receipt,batch,WT,output,rid=RID,expected_argv=child_argv(admission,batch,receipt,output),schema='ft_d07_owned_launch/v2')
 value=json.loads(Path(receipt).read_text());mine=g.process_birth()
 if value.get('child')!=mine or value.get('batch_pid')!=mine['pid'] or value.get('scope')!={'worktree':str(WT),'output_root':str(output)}:raise RuntimeError('receipt birth/worktree/output proof differs')
def controller(admission,gate=None):
 """D07 reserve/publish path; only root may call this after filling admission."""
 if sys.platform!='linux':raise RuntimeError('Linux root controller only')
 g=d07() if gate is None else gate;doc=require_admission(admission);out=Path(doc['prototype_output'])
 if g.LOCK.exists() or g.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists')
 owned=g.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',g.ATOMIC_HELPER_SHA,'d10_v8_atomic');batch=helper.next_batch(g.ROUNDS);receipt=out.parent/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True)
 argv=child_argv(admission,batch,receipt,out);reserved={'schema':'ft_d07_owned_launch/v2','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':g.argv_sha256(argv),'controller':g.process_birth(),'scope':{'worktree':str(WT),'output_root':str(out)}}
 got=owned.reserve_process(helper,batch,RID,argv,receipt,reserved);birth=owned.process_identity(got['batch_pid'])
 if not birth or birth.get('pid')!=got['batch_pid']:raise RuntimeError('D07 reserved birth differs')
 return g.publish_child_binding(receipt,got,{'pid':birth['pid'],'start_ticks':birth['start_ticks'],'execution_id':f"{birth['pid']}:{birth['start_ticks']}"},lifecycle=owned)
def wait_cleanup_idle(g, timeout=120):
 deadline=time.monotonic()+timeout
 while True:
  try:g.require_gpu_idle();return
  except RuntimeError:
   if time.monotonic()>=deadline:raise
   time.sleep(1)
def branch_event(event,g,proc):
 e=json.loads(event.read_text());birth=e.get('engine_birth');ident=g.process_identity(birth.get('pid')) if isinstance(birth,dict) else None
 if not (e.get('schema')=='ft_d10_branch_event/v4' and e.get('method')=='Engine._forward_d10_staggered_decode' and e.get('entered') is True and e.get('actual_batch_reqs')==2 and e.get('actual_can_use_d10_staggered') is True and e.get('candidate_commit')==CANDIDATE and isinstance(ident,dict) and ident.get('start_ticks')==birth.get('start_ticks') and ident.get('pgid')==proc.pid and e.get('engine_pgid')==proc.pid and birth.get('pid')!=proc.pid):raise ValueError('branch event identity differs')
 return e
class Default:
 def __init__(self):self.gate=d07();self.run=runner()
 def start(self,a,c,e,l):
  with l.open('xb') as h:return subprocess.Popen(['taskset','-c','1,3-47',*a],cwd=c,env=e,stdin=subprocess.DEVNULL,stdout=h,stderr=subprocess.STDOUT,start_new_session=True)
 def health(self,e,timeout=10):
  with build_opener(ProxyHandler({})).open(e+'/health',timeout=timeout) as r:return json.loads(r.read())
 def dispatch(self,e,out,i,timeout):
  inp=self.run.ORIGINAL if i<2 else self.run.FIXED;c=self.run.argv(e,str(out/f'profile{i}'),inp);put(out/f'profile{i}.command.json',{'argv':c,'input_sha256':sha(inp)});z=subprocess.run(c,timeout=timeout);put(out/f'profile{i}.exit.json',{'exit_code':z.returncode});
  if z.returncode:raise RuntimeError('AIPerf failed')
 def stop(self,p):self.gate.load_owned_lifecycle().stop_owned_process(p,120,30)
 def alive(self,p):return self.gate.load_owned_lifecycle().owned_group_alive(p)
def group_gate(run,root,i):
 p=root/f'profile{i}';return run.parser().original_gate(p) if i<2 else run.parser().fixed_gate(p)
def child(admission,batch,receipt,deps=None):
 deps=deps or Default();g,run=deps.gate,deps.run;doc=require_admission(admission);out=Path(doc['prototype_output']);svc=doc['service'];calls=0;proc=None;owner=None;err=None;cleanup=None;workload_deadline=time.monotonic()+1350;deadline_cleanup=workload_deadline+150;deadline=workload_deadline
 # Fresh root is recorded before any gate, including wrong-birth/pre-idle failures.
 if out.exists() or out.is_symlink():raise RuntimeError('fresh output required')
 out.mkdir(parents=True);put(out/'preflight.json',{'rid':RID,'admission':str(admission),'batch':batch,'gpu_started':False,'service_started':False})
 try:
  verify_receipt(g,receipt,batch,admission,out)
  if g.LOCK.exists() or g.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists')
  owner=g.take_d07_gpu_lock(RID,batch);g.require_gpu_idle();held=reserve_pair(svc['api_port']);close_pair(held);held=reserve_pair(svc['api_port']);close_pair(held)
  put(out/'admission_snapshot.json',doc);env=g.clean_environment(WT);event=out/'d10_branch_event.json';env.update({'PYTHONPATH':str(HERE)+os.pathsep+str(WT/'python'),'FT_D10_BRANCH_EVENT':str(event),'FT_D10_CANDIDATE':CANDIDATE,'PYTHONDONTWRITEBYTECODE':'1'})
  proc=deps.start([str(ROOT/'venv/bin/python'),str(HERE/'d10_branch_startup_v4.py'),*svc['argv'][2:]],svc['cwd'],env,out/'serve.log');birth=g.process_identity(proc.pid);put(out/'owned_service_birth.json',{'birth':birth,'argv':svc['argv']})
  if not birth or birth.get('pid')!=proc.pid or birth.get('pgid')!=proc.pid:raise RuntimeError('owned service birth differs')
  while time.monotonic()<deadline:
   if proc.poll() is not None:raise RuntimeError('service exited before health')
   try:
    if deps.health(svc['endpoint'],max(1,min(10,int(deadline-time.monotonic())))).get('status')=='ok':break
   except OSError:time.sleep(2)
  else:raise TimeoutError('health timeout')
  a=out/'aiperf';a.mkdir()
  for i in range(4):
   append(out/'budget.jsonl',{'group':i,'calls_before':calls,'calls_after':calls+2});calls+=2;remaining=int(deadline-time.monotonic());
   if remaining<=0:raise TimeoutError('whole workload budget exhausted')
   deps.dispatch(svc['endpoint'],a,i,remaining)
   try:group_gate(run,a,i)
   except RuntimeError as x:raise ValueError(str(x))
   if not event.exists():
    if i==0: continue
   else:branch_event(event,g,proc)
  if not event.exists():raise ValueError('branch event absent after all completed groups')
  branch_event(event,g,proc)
 except ValueError as x:err=('not_met',repr(x))
 except BaseException as x:err=('failed_harness',repr(x))
 finally:
  try:
   if proc:deps.stop(proc);assert not deps.alive(proc.pid)
   wait_cleanup_idle(g, min(120,max(0,deadline_cleanup-time.monotonic())));held=reserve_pair(svc['api_port']);close_pair(held)
  except BaseException as x:cleanup=repr(x)
  verdict='failed_harness' if cleanup or (err and err[0]=='failed_harness') else ('not_met' if err else 'measured_pending_independent_review')
  put(out/'terminal.json',{'rid':RID,'verdict':verdict,'error':None if not err else err[1],'cleanup_error':cleanup,'actual_services':int(proc is not None),'actual_generation_calls':calls,'lock_retained':bool(cleanup),'product_acceptance':False})
  if owner and not cleanup:g.release_d07_gpu_lock(owner)
 if cleanup:raise RuntimeError(cleanup)
 if err:raise RuntimeError(err[1])
 return out/'terminal.json'
def filedry():return {'schema':'ft_d10_v8_filedry/v1','source_sha256':hashes(),'runner_source_sha256':runner().source_hashes(),'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);p.add_argument('--worktree',type=Path);p.add_argument('--output-root',type=Path);a=p.parse_args()
 if a.filedry:print(json.dumps(filedry(),sort_keys=True));return
 if a.run and a.admission and not a.owned_child and a.batch is None and a.launch_receipt is None:controller(a.admission);return
 if a.run and a.owned_child and a.admission and a.batch is not None and a.launch_receipt and a.worktree==WT:child(a.admission,a.batch,a.launch_receipt);return
 p.error('root controller or fully-bound owned child required')
if __name__=='__main__':main()
