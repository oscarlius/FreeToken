"""CPU fake transport exercises the owned controller-child admission and receipt checks."""
import importlib.util,json,os,socket
from pathlib import Path
HERE=Path(__file__).parent;s=importlib.util.spec_from_file_location('owner',HERE/'d10_cache_owned_parent.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def port():
 x=socket.socket();x.bind(('127.0.0.1',0));p=x.getsockname()[1];x.close();return p
def raw(i,n=256):return {'metadata':{'x_request_id':str(i)},'metrics':{'usage_completion_tokens':{'value':n},'output_token_count':{'value':n},'time_to_first_token':{'value':1},'output_token_throughput_per_user':{'value':31}}}
class Helper:
 def next_batch(self,*a):return 1
class Life:
 def __init__(self,g):self.g=g
 def process_identity(self,p):return self.g.process_identity(p)
 def verified_module(self,*a):return Helper()
 def reserve_process(self,helper,batch,rid,argv,receipt,reserved):
  receipt.write_text(json.dumps(reserved|{'state':'launched','batch_pid':999}));return json.loads(receipt.read_text())
 def stop_owned_process(self,*a):pass
 def owned_group_alive(self,*a):return False
class Gate:
 def __init__(self,p):self.LOCK=p/'lock';self.ATOMIC_HELPER_SHA='x';self.ROUNDS=p
 def take_d07_gpu_lock(self,*a):self.LOCK.write_text('x');return 'owner'
 def release_d07_gpu_lock(self,*a):self.LOCK.unlink()
 def require_gpu_idle(self):pass
 def clean_environment(self,*a):return {}
 def process_birth(self):return {'pid':999,'start_ticks':4,'execution_id':'999:4'}
 def process_identity(self,p):return {'pid':p,'start_ticks':4 if p==999 else 3,'pgid':123}
 def load_owned_lifecycle(self):return Life(self)
 def argv_sha256(self,argv):return __import__('hashlib').sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest()
 def publish_child_binding(self,receipt,got,child,lifecycle=None):
  d=json.loads(Path(receipt).read_text());d['child']=child;Path(receipt).write_text(json.dumps(d));return d
 def require_child_receipt(self,receipt,batch,wt,out,**kw):
  d=json.loads(Path(receipt).read_text());assert d['batch']==batch and d['scope']=={'worktree':str(wt),'output_root':str(out)} and d['child']==self.process_birth() and d['argv_sha256']==self.argv_sha256(kw['expected_argv'])
class Proc:
 pid=123
 def poll(self):return None
class Deps:
 def __init__(self,p):self.gate=Gate(p);self.run=m.runner()
 def start(self,*a):return Proc()
 def health(self,*a):return {'status':'ok'}
 def dispatch(self,e,out,i,timeout):
  p=out/f'profile{i}';p.mkdir(exist_ok=True);n=64 if i<2 else 256
  (p/'profile_export.jsonl').write_text('\n'.join(json.dumps(raw(f'{i}-{j}',n)) for j in range(2)))
  (out.parent/'d10_branch_event.json').write_text(json.dumps({'schema':'ft_d10_branch_event/v4','method':'Engine._forward_d10_staggered_decode','entered':True,'actual_batch_reqs':2,'actual_can_use_d10_staggered':True,'candidate_commit':m.CANDIDATE,'engine_birth':{'pid':999,'start_ticks':4},'engine_pgid':123}))
 def stop(self,*a):pass
 def alive(self,*a):return False
def test_actual_admission_and_receipt_cpu(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'reserve_pair',lambda _ : [])
 m.RUNS=tmp_path/'runs';m.RUNS.mkdir();p=port();out=m.RUNS/'out';doc={'schema':'ft_d10_cache_prototype_admission/v2','admit':True,'rid':m.RID,'candidate':m.CANDIDATE,'parent':m.PARENT,'flag':m.FLAG,'calls_max':8,'services_max':1,'source_sha256':m.hashes(),'runner_source_sha256':m.runner().source_hashes(),'candidate_proof':m.candidate_proof(),'prototype_output':str(out),'service':{'api_port':p,'tcpstore_port':p+1,'endpoint':f'http://127.0.0.1:{p}','cwd':str(m.WT),'argv':['ft','serve','--d10-staggered-decode','--port',str(p)],'affinity':{'argv':['taskset','-c','1,3-47']}}}
 admission=tmp_path/'admission.json';admission.write_text(json.dumps(doc));os.chmod(admission,0o444)
 receipt=tmp_path/'receipt.json';receipt.write_text(json.dumps({'batch':1,'child':{'pid':999,'start_ticks':4,'execution_id':'999:4'},'batch_pid':999,'argv_sha256':Gate(tmp_path).argv_sha256(m.child_argv(admission,1,receipt,out)),'scope':{'worktree':str(m.WT),'output_root':str(out)}}))
 term=json.loads(m.child(admission,1,receipt,Deps(tmp_path)).read_text());assert term['verdict']=='measured_pending_independent_review' and term['actual_generation_calls']==8

def test_frozen_ft_argv_has_no_taskset():
 argv=['ft','serve','--d10-staggered-decode','--port','12345'];assert argv[:2]==['ft','serve'] and 'taskset' not in argv

def test_controller_publish_then_child_and_tamper_rejected(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'reserve_pair',lambda _ : [])
 m.RUNS=tmp_path/'runs';m.RUNS.mkdir();p=port();out=m.RUNS/'out';doc={'schema':'ft_d10_cache_prototype_admission/v2','admit':True,'rid':m.RID,'candidate':m.CANDIDATE,'parent':m.PARENT,'flag':m.FLAG,'calls_max':8,'services_max':1,'source_sha256':m.hashes(),'runner_source_sha256':m.runner().source_hashes(),'candidate_proof':m.candidate_proof(),'prototype_output':str(out),'service':{'api_port':p,'tcpstore_port':p+1,'endpoint':f'http://127.0.0.1:{p}','cwd':str(m.WT),'argv':['ft','serve','--d10-staggered-decode','--port',str(p)],'affinity':{'argv':['taskset','-c','1,3-47']}}}
 admission=tmp_path/'admission2.json';admission.write_text(json.dumps(doc));os.chmod(admission,0o444);gate=Gate(tmp_path);binding=m.controller(admission,gate=gate);receipt=out.parent/f'launch_{m.RID}_batch1.json';assert binding['child']=={'pid':999,'start_ticks':4,'execution_id':'999:4'}
 assert json.loads(m.child(admission,1,receipt,Deps(tmp_path)).read_text())['actual_generation_calls']==8
 bad=json.loads(receipt.read_text());bad['child']['start_ticks']=5;receipt.write_text(json.dumps(bad));out2=m.RUNS/'out2';doc['prototype_output']=str(out2);admission2=tmp_path/'admission3.json';admission2.write_text(json.dumps(doc));os.chmod(admission2,0o444)
 import pytest
 with pytest.raises(RuntimeError):m.child(admission2,1,receipt,Deps(tmp_path))


def test_imported_d07_receipt_verifier_canonical_and_wrong_ticks(monkeypatch,tmp_path):
 d=m.d07();birth={'pid':4242,'start_ticks':77,'execution_id':'4242:77'};monkeypatch.setattr(d,'process_birth',lambda:birth)
 receipt=tmp_path/'actual_d07_receipt.json';argv=m.child_argv(tmp_path/'admission',3,receipt,tmp_path/'out')
 good={'schema':'ft_d07_owned_launch/v2','state':'launched','rid':m.RID,'batch':3,'batch_pid':4242,'candidate_commit':m.CANDIDATE,'argv_sha256':d.argv_sha256(argv),'child':birth};receipt.write_text(json.dumps(good))
 assert d.require_child_receipt(receipt,3,m.WT,tmp_path/'out',rid=m.RID,expected_argv=argv,schema='ft_d07_owned_launch/v2')['child']==birth
 bad={**good,'child':{**birth,'start_ticks':78}};receipt.write_text(json.dumps(bad));ticks=iter((0,31));monkeypatch.setattr(d.time,'monotonic',lambda:next(ticks));monkeypatch.setattr(d.time,'sleep',lambda _:None)
 import pytest
 with pytest.raises(RuntimeError,match='lacks its controller-bound launch receipt'):d.require_child_receipt(receipt,3,m.WT,tmp_path/'out',rid=m.RID,expected_argv=argv,schema='ft_d07_owned_launch/v2')


def test_cleanup_idle_delayed_uses_real_helper(monkeypatch):
 class G:
  def __init__(self):self.n=0
  def require_gpu_idle(self):
   self.n+=1
   if self.n<4:raise RuntimeError('driver draining')
 g=G();clock=iter((0,1,2,3));monkeypatch.setattr(m.time,'monotonic',lambda:next(clock));monkeypatch.setattr(m.time,'sleep',lambda _:None);m.wait_cleanup_idle(g,120);assert g.n==4
def test_cleanup_idle_stuck_deadline_rejects(monkeypatch):
 class G:
  def require_gpu_idle(self):raise RuntimeError('busy')
 clock=iter((0,121));monkeypatch.setattr(m.time,'monotonic',lambda:next(clock));monkeypatch.setattr(m.time,'sleep',lambda _:None)
 import pytest
 with pytest.raises(RuntimeError,match='busy'):m.wait_cleanup_idle(G(),120)

def admission_doc(tmp_path, out):
 p=port()
 return {'schema':'ft_d10_cache_prototype_admission/v2','admit':True,'rid':m.RID,'candidate':m.CANDIDATE,'parent':m.PARENT,'flag':m.FLAG,'calls_max':8,'services_max':1,'source_sha256':m.hashes(),'runner_source_sha256':m.runner().source_hashes(),'candidate_proof':m.candidate_proof(),'prototype_output':str(out),'service':{'api_port':p,'tcpstore_port':p+1,'endpoint':f'http://127.0.0.1:{p}','cwd':str(m.WT),'argv':['ft','serve','--d10-staggered-decode','--port',str(p)],'affinity':{'argv':['taskset','-c','1,3-47']}}}
def child_receipt(tmp_path, admission, out, batch=1):
 receipt=tmp_path/'receipt.json';g=Gate(tmp_path)
 receipt.write_text(json.dumps({'batch':batch,'child':{'pid':999,'start_ticks':4,'execution_id':'999:4'},'batch_pid':999,'argv_sha256':g.argv_sha256(m.child_argv(admission,batch,receipt,out)),'scope':{'worktree':str(m.WT),'output_root':str(out)}}))
 return receipt
class DelayedCleanupGate(Gate):
 def __init__(self,p):super().__init__(p);self.idle_calls=0
 def require_gpu_idle(self):
  self.idle_calls+=1
  if 1<self.idle_calls<5:raise RuntimeError('driver draining')
class ChildDeps(Deps):
 def __init__(self,p,gate):super().__init__(p);self.gate=gate;self.dispatched=[]
 def dispatch(self,*a):self.dispatched.append(a[2]);return super().dispatch(*a)
def test_actual_child_delayed_gpu_cleanup_uses_real_helper(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'reserve_pair',lambda _ : []);clock=[0];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(m.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
 m.RUNS=tmp_path/'runs';m.RUNS.mkdir();out=m.RUNS/'out';doc=admission_doc(tmp_path,out);admission=tmp_path/'admission.json';admission.write_text(json.dumps(doc));os.chmod(admission,0o444);gate=DelayedCleanupGate(tmp_path);deps=ChildDeps(tmp_path,gate)
 terminal=json.loads(m.child(admission,1,child_receipt(tmp_path,admission,out),deps).read_text())
 assert terminal['verdict']=='measured_pending_independent_review' and gate.idle_calls==5 and not gate.LOCK.exists()
def test_actual_child_busy_cleanup_retains_lock_and_fails_harness(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'reserve_pair',lambda _ : []);clock=[0];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(m.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
 m.RUNS=tmp_path/'runs';m.RUNS.mkdir();out=m.RUNS/'out';doc=admission_doc(tmp_path,out);admission=tmp_path/'admission.json';admission.write_text(json.dumps(doc));os.chmod(admission,0o444)
 class BusyGate(DelayedCleanupGate):
  def require_gpu_idle(self):
   self.idle_calls+=1
   if self.idle_calls>1:raise RuntimeError('GPU remains busy')
 gate=BusyGate(tmp_path)
 import pytest
 with pytest.raises(RuntimeError,match='GPU remains busy'):m.child(admission,1,child_receipt(tmp_path,admission,out),ChildDeps(tmp_path,gate))
 terminal=json.loads((out/'terminal.json').read_text());assert terminal['verdict']=='failed_harness' and terminal['lock_retained'] is True and gate.LOCK.exists() and gate.idle_calls==122
def test_actual_child_whole_budget_stops_before_next_dispatch_and_cleans_within_reserve(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'reserve_pair',lambda _ : []);clock=[0];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(m.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
 m.RUNS=tmp_path/'runs';m.RUNS.mkdir();out=m.RUNS/'out';doc=admission_doc(tmp_path,out);admission=tmp_path/'admission.json';admission.write_text(json.dumps(doc));os.chmod(admission,0o444);gate=Gate(tmp_path)
 class BudgetDeps(ChildDeps):
  def dispatch(self,*a):
   super().dispatch(*a);clock[0]=1351
 deps=BudgetDeps(tmp_path,gate)
 import pytest
 with pytest.raises(RuntimeError,match='whole workload budget exhausted'):m.child(admission,1,child_receipt(tmp_path,admission,out),deps)
 terminal=json.loads((out/'terminal.json').read_text());assert deps.dispatched==[0] and terminal['verdict']=='failed_harness' and not gate.LOCK.exists() and clock[0]<=1500
