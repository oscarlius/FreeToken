import importlib.util,json,socket
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('v8',HERE/'d10_prototype_owned_parent_v8.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def port():
 x=socket.socket();x.bind(('127.0.0.1',0));p=x.getsockname()[1];x.close();return p
def raw(i,n,speed):return {'metadata':{'x_request_id':str(i)},'metrics':{'usage_completion_tokens':{'value':n},'output_token_count':{'value':n},'time_to_first_token':{'value':1},'output_token_throughput_per_user':{'value':speed}}}
def profile(path,i,n,speed):path.mkdir(exist_ok=True);(path/'profile_export.jsonl').write_text('\n'.join(json.dumps(raw(f'{i}-{j}',n,speed)) for j in range(2)))
class Life:
 def stop_owned_process(self,*_):pass
 def owned_group_alive(self,*_):return False
class Gate:
 def __init__(self,root,mode):self.LOCK=root/'lock';self.mode=mode;self.released=False
 def require_child_receipt(self,*_,**__):
  if self.mode=='birth':raise RuntimeError('wrong birth')
 def take_d07_gpu_lock(self,*_):self.LOCK.write_text('x');return {'x':1}
 def release_d07_gpu_lock(self,*_):self.released=True;self.LOCK.unlink()
 def require_gpu_idle(self):
  if self.mode in ('preidle','postidle') and (self.mode=='preidle' or getattr(self,'stopped',False)):raise RuntimeError('gpu busy')
 def clean_environment(self,*_):return {}
 def process_identity(self,pid):return {'pid':pid,'start_ticks':3 if pid==999 else 2,'pgid':123}
 def load_owned_lifecycle(self):return Life()
class Proc:
 pid=123
 def poll(self):return None
class Deps:
 def __init__(self,root,doc,mode):self.gate=Gate(root,mode);self.run=m.runner();self.doc=doc;self.mode=mode;self.calls=[]
 def start(self,*_):return Proc()
 def health(self,*_):return {'status':'ok'}
 def dispatch(self,_,out,i):
  self.calls.append(i);p=out/f'profile{i}';profile(p,i,64 if i<2 else 256,1 if self.mode=='slow' else 31)
  if self.mode!='noevent':(Path(self.doc['prototype_output'])/'d10_branch_event.json').write_text(json.dumps({'schema':'ft_d10_branch_event/v4','method':'Engine._forward_d10_staggered_decode','entered':True,'actual_batch_reqs':2,'actual_can_use_d10_staggered':True,'candidate_commit':m.CANDIDATE,'engine_birth':{'pid':999,'start_ticks':3},'engine_pgid':123}))
 def stop(self,*_):self.gate.stopped=True
 def alive(self,*_):return False
def doc(tmp):
 p=port();return {'prototype_output':str(tmp/'out'),'service':{'api_port':p,'tcpstore_port':p+1,'endpoint':f'http://127.0.0.1:{p}','cwd':str(tmp),'argv':['ft','serve','--port',str(p),m.FLAG]}}
@pytest.mark.parametrize('mode,verdict,calls',[('slow','not_met',2),('birth','failed_harness',0),('preidle','failed_harness',0),('postidle','failed_harness',8)])
def test_same_body_negative_terminal_and_stop(monkeypatch,tmp_path,mode,verdict,calls):
 d=doc(tmp_path);monkeypatch.setattr(m,'require_admission',lambda _:d)
 if mode!='birth':monkeypatch.setattr(m,'verify_receipt',lambda *a: None)
 deps=Deps(tmp_path,d,mode)
 with pytest.raises(RuntimeError):m.child(tmp_path/'admit',1,tmp_path/'receipt',deps)
 term=json.loads((Path(d['prototype_output'])/'terminal.json').read_text());assert term['verdict']==verdict and term['actual_generation_calls']==calls
 assert deps.gate.released is (mode not in ('birth','preidle','postidle'))
def test_v8_contains_canonical_and_event_identity_guards():
 text=(HERE/'d10_prototype_owned_parent_v8.py').read_text()
 for token in ('MANIFEST.sha256','round_history','D09_T16_RETRY1_OWNED_CLEANUP_READBACK.json','native provenance exact binding','engine_pgid','birth.get(\'pid\')!=proc.pid','calls_after') :assert token in text
