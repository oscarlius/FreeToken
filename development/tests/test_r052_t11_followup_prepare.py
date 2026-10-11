import importlib.util
from pathlib import Path
import pytest
import types,json
p=Path(__file__).parents[1]/'r052_t11_followup_prepare.py';s=importlib.util.spec_from_file_location('r052',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
REAL_DRY_RECEIPT=m.require_dry_run_receipt
REAL_STARTUP_REVIEW=m.require_startup_review
@pytest.fixture(autouse=True)
def _review_gate(monkeypatch):
 monkeypatch.setattr(m,'require_dry_run_receipt',lambda:{'path':'dry','sha256':'d'*64})
 monkeypatch.setattr(m,'require_startup_review',lambda receipt:{'path':'review','sha256':'r'*64})
def target():return {'uid':7,'prompt_tokens':13432,'completion_tokens':200,'messages':[{'role':'user','content':'p'}],'text':'answer','trace_index':7,'history_uid':8}
def test_actual_followup_binds_prompt_output_and_new_user_message():
 x=m.followup_messages(target());assert x[-2]['content']=='answer' and x[-1]['role']=='user'
def test_hhook_and_hbug_use_actual_cached_tokens():
 assert m.classify(target(),{'cached_tokens':13700})['classification']=='H-hook';assert m.classify(target(),{'cached_tokens':13376})['classification']=='H-bug'
def test_overlapping_or_undefined_hypothesis_bounds_are_rejected():
 with pytest.raises(RuntimeError,match='do not distinguish'):m.classify({**target(),'prompt_tokens':13376,'completion_tokens':56},{'cached_tokens':13376})
 with pytest.raises(RuntimeError,match='do not distinguish'):m.classify(target(),{'cached_tokens':13440})
def test_missing_actual_fields_rejected():
 with pytest.raises(ValueError):m.classify(target(),{})
 with pytest.raises(ValueError):m.followup_messages({'messages':[],'text':''})
def test_execute_followup_sends_target_prompt_then_output_then_new_user():
 seen=[]
 result=m.execute_followup(target(),lambda messages:(seen.append(messages) or {'cached_tokens':13700}))
 assert result['actual_response']['cached_tokens']==13700 and seen[0][0]['content']=='p' and seen[0][-2]['content']=='answer' and seen[0][-1]['role']=='user'
def test_execute_followup_rejects_non_target_uid():
 with pytest.raises(ValueError):m.execute_followup({**target(),'trace_index':6},lambda _:{'cached_tokens':1})
def test_controller_reserves_once_and_publishes_child(monkeypatch,tmp_path):
 proof=tmp_path/'p';proof.write_text('{}');seen=[]
 class O:
  def verified_module(self,*_):return types.SimpleNamespace(next_batch=lambda _:81)
  def reserve_process(self,*a):seen.append(a);return {**a[-1],'batch_pid':222}
  def process_identity(self,_):return {'pid':222,'start_ticks':9}
  def publish_receipt(self,*_):pass
 class D:
  ATOMIC_HELPER_SHA='x';LOCK=tmp_path/'none'
  def require_r041_kept(self,_):return proof
  def require_t20_failed_harness(self):return proof
  def require_closed_round(self,*_):return proof
  def checked_worktree(self,*_):return {}
  def load_owned_lifecycle(self):return O()
  def argv_sha256(self,_):return 'argv'
  def process_birth(self):return {'pid':1,'start_ticks':2}
  def publish_child_binding(self,_p,r,c,**_):return {**r,'child':c}
 monkeypatch.setattr(m,'load_d07',lambda:D());monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds')
 got=m.dispatch();assert len(seen)==1 and got['batch']==81 and got['child']['pid']==222
def test_foreign_lock_rejects_before_batch(monkeypatch,tmp_path):
 lock=tmp_path/'lock';lock.write_text('x')
 class D:
  LOCK=lock
  def require_r041_kept(self,_):return tmp_path/'p'
  def require_t20_failed_harness(self):return tmp_path/'p'
  def require_closed_round(self,*_):return tmp_path/'p'
  def checked_worktree(self,*_):return {}
  def load_owned_lifecycle(self):pytest.fail('must not allocate')
 monkeypatch.setattr(m,'load_d07',lambda:D())
 with pytest.raises(RuntimeError,match='foreign GPU lock'):m.dispatch()
def test_invalid_receipt_rejects_before_body(monkeypatch,tmp_path):
 class D:
  def require_child_receipt(self,*_a,**_k):raise RuntimeError('bad receipt')
 monkeypatch.setattr(m,'load_d07',lambda:D())
 with pytest.raises(RuntimeError,match='bad receipt'):m.dispatch(owned_child=True,batch=1,receipt=tmp_path/'x',body=lambda:pytest.fail('body'))
def test_body_runs_replay_then_one_followup_then_cleanup(monkeypatch,tmp_path):
 order=[];proc=types.SimpleNamespace(pid=9)
 class D:
  def take_d07_gpu_lock(self,*_):order.append('lock');return {}
  def require_gpu_idle(self):order.append('idle')
  def dynamic_fixture_port(self):return 45678
  def release_d07_gpu_lock(self,_):order.append('unlock')
  def load_owned_lifecycle(self):return types.SimpleNamespace(stop_owned_process=lambda _:order.append('stop'),owned_group_alive=lambda _:False)
  def write_new(self,p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
 class R:
  def bind_trace(self,r):order.append('bind');return 'trace'
  def client_module(self,_):order.append('client');return object()
  def private_port_pair(self):return 45678,{'api':45678,'tcpstore':45679}
  def start_service(self,*_):order.append('server');return proc
  def replay_to_target(self,*_):order.append('replay');return target()
  def followup(self,*_):order.append('follow');return {'uid':9,'cached_tokens':13700}
  def d0_evidence(self,_):order.append('d0');return {'ok':True}
  def confirm_cache_evidence(self,*_):order.append('confirm');return {'ok':True}
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds')
 out=m.run_owned_body(D(),2,replay=R());assert out['classification']=='H-hook' and order==['lock','idle','bind','client','server','replay','follow','stop','unlock','d0','confirm'] and (tmp_path/'rounds'/m.RID/'followup_raw.json').is_file()
def test_followup_raw_is_preserved_before_d0_confirmation_rejects(monkeypatch,tmp_path):
 proc=types.SimpleNamespace(pid=9)
 class D:
  def take_d07_gpu_lock(self,*_):return {}
  def require_gpu_idle(self):pass
  def dynamic_fixture_port(self):return 45678
  def release_d07_gpu_lock(self,_):pass
  def load_owned_lifecycle(self):return types.SimpleNamespace(stop_owned_process=lambda _:None,owned_group_alive=lambda _:False)
  def write_new(self,p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
 class R:
  def bind_trace(self,_):return 'trace'
  def client_module(self,_):return object()
  def private_port_pair(self):return 45678,{'api':45678,'tcpstore':45679}
  def start_service(self,*_):return proc
  def replay_to_target(self,*_):return target()
  def followup(self,*_):return {'uid':9,'prompt_tokens':50,'completion_tokens':1,'cached_tokens':None,'stream_events':[{'id':'chatcmpl-9'}],'payload':{},'response':{'usage':{}}}
  def d0_evidence(self,_):return {'prefill_requests':{}}
  def confirm_cache_evidence(self,*_):raise RuntimeError('D0 mismatch')
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds')
 with pytest.raises(RuntimeError,match='D0 mismatch'):m.run_owned_body(D(),2,replay=R())
 raw=tmp_path/'rounds'/m.RID/'followup_raw.json'
 assert raw.is_file() and json.loads(raw.read_text())['uid']==9
def test_actual_uid7_can_be_bound_before_final_d0_classification():
 row={**target(),'uid':7};assert m.execute_followup(row,lambda _:{'uid':8,'cached_tokens':13376})['actual_response']['uid']==8
def test_stop_failure_preserves_lock_even_if_group_now_absent(monkeypatch,tmp_path):
 calls=[];proc=types.SimpleNamespace(pid=5)
 class D:
  def take_d07_gpu_lock(self,*_):return {}
  def require_gpu_idle(self):pass
  def dynamic_fixture_port(self):return 1
  def release_d07_gpu_lock(self,_):calls.append('unlock')
  def load_owned_lifecycle(self):return types.SimpleNamespace(stop_owned_process=lambda _:(_ for _ in ()).throw(RuntimeError('stop')),owned_group_alive=lambda _:False)
  def write_new(self,p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
 class R:
  def bind_trace(self,_):return 't'
  def client_module(self,_):return object()
  def private_port_pair(self):return 45678,{'api':45678,'tcpstore':45679}
  def start_service(self,*_):return proc
  def replay_to_target(self,*_):return target()
  def followup(self,*_):return {'uid':9,'cached_tokens':13376}
  def d0_evidence(self,_):return {}
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'r')
 with pytest.raises(RuntimeError,match='preserve GPU lock'):m.run_owned_body(D(),1,replay=R())
 assert not calls and json.loads((tmp_path/'r'/m.RID/'owned_cleanup.json').read_text())['lock_released'] is False
def test_start_failure_owned_process_is_stopped_and_lock_preserved(monkeypatch,tmp_path):
 calls=[];proc=types.SimpleNamespace(pid=6)
 class D:
  def take_d07_gpu_lock(self,*_):return {}
  def require_gpu_idle(self):pass
  def dynamic_fixture_port(self):return 1
  def release_d07_gpu_lock(self,_):calls.append('unlock')
  def load_owned_lifecycle(self):return types.SimpleNamespace(stop_owned_process=lambda p:(calls.append(p) or (_ for _ in ()).throw(RuntimeError('stop'))),owned_group_alive=lambda _:False)
  def write_new(self,p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))
 class R:
  def bind_trace(self,_):return 't'
  def client_module(self,_):return object()
  def private_port_pair(self):return 45678,{'api':45678,'tcpstore':45679}
  def start_service(self,*_):
   e=RuntimeError('start');e.owned_process=proc;raise e
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'r')
 with pytest.raises(RuntimeError,match='preserve GPU lock'):m.run_owned_body(D(),1,replay=R())
 run=tmp_path/'r'/m.RID
 assert calls==[proc] and json.loads((run/'owned_cleanup.json').read_text())['lock_released'] is False and (run/'failed_harness.json').is_file()

def test_cli_dispatches_receipt_owned_child_and_rejects_incomplete_args(monkeypatch,tmp_path):
 seen=[]
 monkeypatch.setattr(m.sys,'platform','linux')
 monkeypatch.setattr(m,'dispatch',lambda **kw:seen.append(kw) or {'pending':True})
 receipt=tmp_path/'launch.json'
 assert m.main(['--run','--owned-child','--batch','72','--launch-receipt',str(receipt)])==0
 assert seen==[{'owned_child':True,'batch':72,'receipt':receipt}]
 with pytest.raises(SystemExit):m.main(['--run','--owned-child','--batch','72'])
 with pytest.raises(SystemExit):m.main(['--run','--batch','72'])
 assert len(seen)==1

def test_cli_controller_uses_owned_dispatch_and_never_target_http_shortcut(monkeypatch):
 seen=[]
 monkeypatch.setattr(m.sys,'platform','linux')
 monkeypatch.setattr(m,'dispatch',lambda **kw:seen.append(kw) or {'queued':True})
 assert m.main(['--run'])==0 and seen==[{'owned_child':False,'batch':None,'receipt':None}]
 with pytest.raises(SystemExit):m.main(['--run','--target-json','unsafe.json','--port','8095'])
 assert len(seen)==1

def test_dry_run_writes_replay_and_service_paths_without_connect(monkeypatch,tmp_path):
 trace=tmp_path/'old_trace.json';trace.write_text('{"rounds":[{}]}')
 class D:
  def checked_worktree(self,_):return {}
  def write_new(self,path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
 class R:
  TRACE_SHA='t'*64
  TRACE=Path('trace_rev.json')
  def target_binding(self,*_):return {'trace_index':7,'history_uid':8,'messages_sha':'e3a67ebe075b0126'}
  def bind_trace(self,path):path.joinpath('trace_input.json').write_text('{}');return {'rounds':[{}]*8}
  def client_module(self,_):return object()
  def private_port_pair(self):return 45678,{'api':45678,'tcpstore':45679}
  def prepare_service_files(self,_,directory,worktree,port,file_dry_run=False):
   for name in ('ENV.json','ENV.txt','SERVE_CMD.txt','serve_argv.json','serve.log'):(directory/name).write_text('{}')
   return {},['ft','serve'],[]
  def dry_replay_outputs(self,directory):
   paths=[]
   for index in range(8):
    path=directory/f'replay_{index:02}.json';path.write_text('{}');paths.append({'path':str(path)})
   path=directory/'followup_raw.json';path.write_text('{}');paths.append({'path':str(path)})
   return paths
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds');monkeypatch.setattr(m,'load_d07',lambda:D());monkeypatch.setattr(m,'replay_module',lambda:R());monkeypatch.setattr(m,'source_hashes',lambda:{'x':'y'})
 def copied(source,target):target.write_text('x');return {'source':str(source),'source_sha256':'x','copy':str(target),'copy_sha256':'x','mode':'0o600'}
 monkeypatch.setattr(m,'copy_source',copied)
 row=m.dry_run();target=m.dry_run_directory()
 assert row['formal_rid_directory_created'] is False and all((target/f'replay_{i:02}.json').is_file() for i in range(8)) and (target/'followup_raw.json').is_file() and not (tmp_path/'rounds'/m.RID).exists()


@pytest.mark.parametrize('old_schema', [False, True])
def test_v5_receipt_requires_reverse_trace_target_and_rejects_v3(monkeypatch,tmp_path,old_schema):
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds');monkeypatch.setattr(m,'source_hashes',lambda:{'source':'sha'})
 tools=m.replay_module();directory=m.dry_run_directory();directory.mkdir(parents=True)
 assert directory.name=='.dryrun_R052_v5_E2-R052'
 row={'schema':'ft_r052_dry_run/v3' if old_schema else 'ft_r052_dry_run/v5','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.PARENT,'passed':True,'source_sha256':m.source_hashes(),'owner':{'path':str(Path(m.__file__).resolve()),'uid':getattr(m.os,'getuid',lambda:None)(),'user':m.os.environ.get('USER') or m.os.environ.get('LOGNAME')},'cwd':str(m.ROOT),'worktree':{'path':str(m.WT),'parent':str(m.WT.parent)},'trace_source':str(tools.TRACE),'trace_sha256':tools.TRACE_SHA,'trace_rounds':12,'port':45678,'port_pair':{'api':45678,'tcpstore':45679},'target_binding':{'trace_index':7,'history_uid':8,'messages_sha':tools.TARGET_MESSAGES_SHA}}
 row.update({k:False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated')})
 path=directory/'dry_run_receipt.json';path.write_text(json.dumps(row));path.chmod(0o444)
 try:
  if old_schema:
   with pytest.raises(RuntimeError,match='identity differs'):REAL_DRY_RECEIPT()
  else:
   assert REAL_DRY_RECEIPT()['path']==str(path)
   path.chmod(0o600);row['trace_source']=str(tools.TRACE.with_name('trace.json'));path.write_text(json.dumps(row));path.chmod(0o444)
   with pytest.raises(RuntimeError,match='identity differs'):REAL_DRY_RECEIPT()
 finally:path.chmod(0o600)

@pytest.mark.parametrize('old_schema',[False,True])
def test_startup_review_v5_rejects_v3_schema(monkeypatch,tmp_path,old_schema):
 monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'source_hashes',lambda:{'source':'sha'})
 receipt={'path':'dry','sha256':'d'*64};path=tmp_path/'runs/dev_R052/reviews/E2-R052_startup_review_v5.json';path.parent.mkdir(parents=True)
 row={'schema':'ft_r052_startup_review/v3' if old_schema else 'ft_r052_startup_review/v5','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.PARENT,'approved':True,'verdict':'PASS','source_sha256':m.source_hashes(),'dry_run_receipt':receipt['path'],'dry_run_receipt_sha256':receipt['sha256']}
 path.write_text(json.dumps(row));path.chmod(0o444)
 try:
  if old_schema:
   with pytest.raises(RuntimeError,match='binding differs'):REAL_STARTUP_REVIEW(receipt)
  else:assert REAL_STARTUP_REVIEW(receipt)['path']==str(path)
 finally:path.chmod(0o600)
