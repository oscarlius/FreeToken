import importlib.util, json, os, sys
from pathlib import Path
import pytest
HERE=Path(__file__).parent
s=importlib.util.spec_from_file_location('t03b_runner',HERE/'runner.py'); m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class T:
 def positive_payload(self):return {'messages':[{'role':'user','content':'x'}]}
 def retained_followup(self,messages,response):return messages
class Proc:
 pid=777
 def poll(self):return None
class Effects:
 def __init__(self, *, snapshots=1, ready_error=None, cleanup_error=None):self.t=T();self.snapshots=snapshots;self.ready_error=ready_error;self.cleanup_error=cleanup_error;self.prepared=[];self.cleaned=[];self.positives=[]
 def prepare(self,arm,index):arm.mkdir();self.prepared.append(index);return ['ft','serve'],{}
 def start(self,arm,index,argv,env):return Proc()
 def ready(self,proc,index,timeout):
  if self.ready_error:raise self.ready_error
 def positive(self,index,payload,timeout):self.positives.append(index);return ({'choices':[{'message':{'reasoning_content':'r','content':'c'}}]},[],0,{'input_sha256':'0'*64})
 def negative(self,index,timeout):return {'ok':True}
 def cleanup(self,arm,index,proc,timeout):
  self.cleaned.append((index,timeout))
  if self.cleanup_error:raise self.cleanup_error
 def evidence(self,arm,turns):return {'snapshots':self.snapshots,'post_trigger_cache_hit':{'uid':1},'trigger':{'classification':'hit'}}
def test_actual_lifecycle_full_frozen_grid_cpu(tmp_path):
 e=Effects();assert m.run_lifecycle(tmp_path/'run',e) is True
 terminal=json.loads((tmp_path/'run/terminal.json').read_text());assert terminal['verdict']=='kept' and terminal['services']==6 and terminal['calls']==24 and e.prepared==list(range(6)) and len(e.cleaned)==6
def test_first_not_met_stops_after_one_service(tmp_path):
 e=Effects(snapshots=0);assert m.run_lifecycle(tmp_path/'run',e) is True
 terminal=json.loads((tmp_path/'run/terminal.json').read_text());assert terminal['verdict']=='not_met' and terminal['services']==1 and terminal['calls']==4 and e.prepared==[0]
def test_ready_failure_runs_cleanup_and_is_failed_harness(tmp_path):
 e=Effects(ready_error=RuntimeError('not ready'));assert m.run_lifecycle(tmp_path/'run',e) is True
 terminal=json.loads((tmp_path/'run/terminal.json').read_text());assert terminal['verdict']=='failed_harness' and terminal['services']==1 and len(e.cleaned)==1 and 'not ready' in terminal['error']
def test_unsafe_cleanup_marks_terminal_unclosed(tmp_path):
 e=Effects(ready_error=RuntimeError('not ready'),cleanup_error=RuntimeError('cleanup bad'));assert m.run_lifecycle(tmp_path/'run',e) is False
 terminal=json.loads((tmp_path/'run/terminal.json').read_text());assert terminal['verdict']=='failed_harness' and terminal['post_cleanup_closed'] is False and 'cleanup bad' in terminal['error']
def test_real_candidate_argparse_and_tcpstore_formula():
 if os.name=='nt':pytest.skip('candidate Linux path is intentionally authoritative')
 sys.path.insert(0,str(m.WT/'python'))
 from freetoken.server.args import parse_args
 argv=m.transport().serve_argv(31601)[2:]+['--enable-toolcall-rolling-ckpt']
 value,_=parse_args(argv)
 assert value.server_port==31601 and value.distributed_addr=='tcp://127.0.0.1:31602' and value.toolcall_rolling_ckpt is True


class ReceiptGate:
 def __init__(self,tmp):self.LOCK=tmp/'lock';self.ROUNDS=tmp;self.ATOMIC_HELPER_SHA='atomic'
 def argv_sha256(self,argv):return m.hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest()
 def process_birth(self):return {'pid':11,'start_ticks':22,'execution_id':'11:22'}
 def process_identity(self,pid):return {'pid':pid,'start_ticks':22,'execution_id':f'{pid}:22'}
 def publish_child_binding(self,path,receipt,child,**kw):
  value={**receipt,'child':child};Path(path).write_text(json.dumps(value));return value
 def load_owned_lifecycle(self):
  outer=self
  class L:
   def verified_module(self,*a):
    class H:
     def next_batch(self,*a):return 9
    return H()
   def reserve_process(self,h,b,r,a,path,reserved):
    value={**reserved,'state':'launched','batch_pid':11};Path(path).write_text(json.dumps(value));return value
  return L()
def test_controller_publishes_canonical_three_key_binding(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'check_admission',lambda *a: {})
 monkeypatch.setattr(m,'candidate',lambda: m.CANDIDATE)
 # keep generated receipt inside the packet while avoiding its existing path.
 monkeypatch.setattr(m,'HERE',tmp_path)
 g=ReceiptGate(tmp_path);receipt=m.controller(tmp_path/'sealed.json',g)
 assert receipt['child']=={'pid':11,'start_ticks':22,'execution_id':'11:22'} and receipt['argv_sha256']==g.argv_sha256(m.child_argv(tmp_path/'sealed.json',9,tmp_path/'runs/launch_batch9.json'))
def test_actual_d07_receipt_verifier_rejects_wrong_birth(tmp_path,monkeypatch):
 if os.name=='nt':pytest.skip('D07 Linux process-birth verifier is authoritative')
 g=m.gate();g.CANDIDATE=m.CANDIDATE;birth={'pid':4242,'start_ticks':77,'execution_id':'4242:77'};monkeypatch.setattr(g,'process_birth',lambda:birth)
 receipt=tmp_path/'receipt.json';argv=m.child_argv(tmp_path/'sealed.json',3,receipt)
 good={'schema':'ft_t03b_morning_launch/v1','state':'launched','rid':m.RID,'batch':3,'batch_pid':4242,'candidate_commit':m.CANDIDATE,'argv_sha256':g.argv_sha256(argv),'child':birth};receipt.write_text(json.dumps(good))
 assert g.require_child_receipt(receipt,3,m.WT,m.ROOT/'runs/dev_T03b',rid=m.RID,expected_argv=argv,schema='ft_t03b_morning_launch/v1')['child']==birth
 receipt.write_text(json.dumps({**good,'child':{**birth,'start_ticks':78}}));ticks=iter((0,31));monkeypatch.setattr(g.time,'monotonic',lambda:next(ticks));monkeypatch.setattr(g.time,'sleep',lambda _:None)
 with pytest.raises(RuntimeError,match='lacks its controller-bound launch receipt'):g.require_child_receipt(receipt,3,m.WT,m.ROOT/'runs/dev_T03b',rid=m.RID,expected_argv=argv,schema='ft_t03b_morning_launch/v1')


def test_frozen_stream_enforces_whole_timeout_without_changing_wire(monkeypatch):
 t=m.transport(); clock=[0]
 class R:
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def __iter__(self):
   clock[0]=2
   yield b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"x"}}]}\n'
   clock[0]=4
   yield b'data: [DONE]\n'
 monkeypatch.setattr(t.urllib.request,'urlopen',lambda *a,**k:R())
 with pytest.raises(TimeoutError,match='transport budget exhausted'):t.stream_request(1,{'model':'x','messages':[]},timeout=3,clock=lambda:clock[0])
def test_cleanup_consumes_one_absolute_deadline(tmp_path,monkeypatch):
 clock=[0];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(m,'require_ports',lambda ports,out,timeout: clock.__setitem__(0,clock[0]+timeout))
 class G:
  def require_gpu_idle(self):
   if clock[0] > 10: raise RuntimeError('late GPU wait')
  def load_owned_lifecycle(self):
   class L:
    def stop_owned_process(self,*a):clock[0]+=8
    def owned_group_alive(self,*a):return False
   return L()
 e=m.Effects(G());e.t=object()
 e.cleanup(tmp_path,0,Proc(),10)
 assert clock[0] == 10

def test_generation_phase_deadline_stops_before_second_request(tmp_path,monkeypatch):
 clock=[0];monkeypatch.setattr(m.time,'monotonic',lambda:clock[0])
 class Slow(Effects):
  def positive(self,index,payload,timeout):
   value=super().positive(index,payload,timeout);clock[0]=m.GENERATION_PHASE_SECONDS+1;return value
 e=Slow()
 assert m.run_lifecycle(tmp_path/'run',e) is True
 terminal=json.loads((tmp_path/'run/terminal.json').read_text())
 assert terminal['verdict']=='failed_harness' and terminal['calls']==1 and e.prepared==[0] and len(e.cleaned)==1 and 'generation phase budget exhausted' in terminal['error']
