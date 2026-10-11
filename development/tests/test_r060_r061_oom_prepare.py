import importlib.util
import json
import os
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

DEV=Path(__file__).parents[1]
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,DEV/file);mod=importlib.util.module_from_spec(spec);assert spec.loader;sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def test_r060_pending_commit_is_inert_and_four_arms_are_exact():
 m=load('r060','r060_oom_t16_prepare_v1.py');value=m.plan()
 assert value['state']=='pending_candidate_commit' and value['default_recovery_enabled'] is True
 assert {(x['tree'],x['d0']) for x in value['arms']}=={('base',False),('base',True),('candidate',False),('candidate',True)}
 assert value['cold']=={'requested_tokens':32052,'expected_input_tokens':32064,'completion_tokens':128,'temperature':0}

def test_r060_rejects_unstable_candidate_and_compares_fulltext_tokens(tmp_path):
 m=load('r060_bind','r060_oom_t16_prepare_v1.py')
 with pytest.raises(RuntimeError):m.candidate_binding('short',tmp_path)
 wt=tmp_path/'wt';wt.mkdir();bound=m.candidate_binding('a'*40,wt);assert bound['candidate_commit']=='a'*40
 good={'input_tokens':32064,'completion_tokens':128,'temperature':0,'cached_tokens':0,'full_text':'same','token_ids':[1]*128}
 assert m.compare_cold(good,dict(good))['token_ids_equal']
 with pytest.raises(RuntimeError):m.compare_cold(good,{**good,'token_ids':[2]*128})
 assert m.validate_d0({'prefill':[{'h2d_bytes':2,'d2d_bytes':3}]})['h2d_bytes']==2

def test_r060_file_dry_uses_writer_and_never_service_or_batch(tmp_path):
 m=load('r060_dry','r060_oom_t16_prepare_v1.py');wt=tmp_path/'wt';wt.mkdir();writes=[]
 def writer(path,value):
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));writes.append(path)
 value=m.file_dry(tmp_path/'dry','b'*40,wt,writer)
 assert value['service_started'] is False and value['gpu_lock_taken'] is False and len(writes)==6
 assert m.plan('b'*40,wt)['multi_probe']['completion_tokens_each']==128

def test_r060_default_formal_writer_is_exclusive_writable_and_source_safe(tmp_path):
 m=load('r060_writer','r060_oom_t16_prepare_v1.py');wt=tmp_path/'wt';wt.mkdir()
 receipt=m.file_dry(tmp_path/'dry','c'*40,wt)
 plan=tmp_path/'dry'/'plan.json'
 assert receipt['plan_sha256']==m.sha(plan) and os.access(plan,os.W_OK)
 if os.name!='nt': assert plan.stat().st_mode & 0o777==0o600
 with pytest.raises(FileExistsError):m.write_new(plan,{})

def test_r060_controller_publishes_birth_bound_receipt_before_child_lock(tmp_path,monkeypatch):
 m=load('r060_launch','r060_oom_t16_prepare_v1.py'); wt=tmp_path/'candidate';wt.mkdir(); calls=[]
 monkeypatch.setattr(m.sys,'platform','linux'); monkeypatch.setattr(m,'ROOT',tmp_path); monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds')
 class Owned:
  def verified_module(self,*_): return SimpleNamespace(next_batch=lambda root:73)
  def reserve_process(self,helper,batch,rid,argv,path,value): calls.append(('reserve',batch,argv)); path.parent.mkdir(parents=True,exist_ok=True); value={**value,'state':'launched','batch_pid':222};path.write_text(json.dumps(value));return value
  def process_identity(self,pid): return {'pid':pid,'start_ticks':33}
  def publish_receipt(self,path,inode,value): calls.append(('publish',value['child']));path.write_text(json.dumps(value))
 def publish(path,receipt,child,*,lifecycle):
  lifecycle.publish_receipt(path,(1,2),{**receipt,'child':child});return {**receipt,'child':child}
 d=SimpleNamespace(LOCK=tmp_path/'gpu.lock',ATOMIC_HELPER_SHA='x',argv_sha256=lambda x:'argv',process_birth=lambda:{'pid':1,'start_ticks':2,'execution_id':'1:2'},load_owned_lifecycle=lambda:Owned(),publish_child_binding=publish)
 monkeypatch.setattr(m,'load_d07',lambda *_:d);monkeypatch.setattr(m,'require_r060_native_provenance',lambda *_:{})
 result=m.controller(m.CANDIDATE,wt)
 assert calls[0][0]=='reserve' and calls[1]==('publish',{'pid':222,'start_ticks':33,'execution_id':'222:33'}) and result['child']['pid']==222

def test_r060_child_rejects_bad_receipt_before_execution(tmp_path,monkeypatch):
 m=load('r060_child','r060_oom_t16_prepare_v1.py'); wt=tmp_path/'candidate';wt.mkdir(); calls=[]
 monkeypatch.setattr(m.sys,'platform','linux')
 d=SimpleNamespace(require_child_receipt=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('bad receipt')))
 monkeypatch.setattr(m,'load_d07',lambda *_:d); monkeypatch.setattr(m,'run_t16_arms',lambda *a,**k: calls.append('body'))
 monkeypatch.setattr(m,'require_r060_native_provenance',lambda *_:{})
 with pytest.raises(RuntimeError,match='bad receipt'):m.child(7,tmp_path/'receipt',m.CANDIDATE,wt)
 assert calls==[]

def ordinary_fixture(tmp_path, uid, tokens=(1,2), text='same'):
    api=tmp_path/f"{uid}.api.json"; sse=tmp_path/f"{uid}.sse"
    rows=['data: '+json.dumps({'choices':[{'delta':{'content':text}}]}), 'data: [DONE]']
    sse.write_text('\n'.join(rows)+'\n',encoding='utf-8')
    api.write_text(json.dumps({'sse':str(sse)}),encoding='utf-8')
    return {'schema':'ft_t06_ordinary_binding/v3','verdict':'worker_input_uid_token_bound','api':{'uid':uid,'path':str(api)},'token_sidecar':{'events':[{'next_token':x} for x in tokens]}}

def test_r061_fault_startup_delegates_to_observer_and_event_is_single(tmp_path):
 m=load('r061','r061_oom_fault_prepare_v1.py'); source=m.write_fault_startup(tmp_path/'run')
 text=Path(source['startup']).read_text()
 assert 'Engine.forward_batch' not in text and 'torch.cuda.OutOfMemoryError' not in text and 'R046C_T06_OBSERVER_DIR' in text and "__mp_main__" in text
 event=tmp_path/'event.json';event.write_text(json.dumps({'schema':'ft_dev_oom_receipt/v1','uid':1,'epoch':1,'point':'before_forward','count':1,'pid':7,'wall_time_ns':1,'monotonic_ns':1}))
 assert m.require_injection_event(event,1)['uid']==1
 event.write_text(json.dumps({'schema':'ft_dev_oom_receipt/v1','uid':1,'epoch':0,'point':'before_forward','count':1,'pid':7,'wall_time_ns':1,'monotonic_ns':1}))
 with pytest.raises(RuntimeError):m.require_injection_event(event,1)

def test_r061_requires_raw_ordinary_sidecar_and_exact_reference_output(tmp_path):
 m=load('r061_bind','r061_oom_fault_prepare_v1.py');before=m.ordinary_binding(ordinary_fixture(tmp_path,3));after=m.ordinary_binding(ordinary_fixture(tmp_path,4))
 birth={'pid':99,'start_ticks':20,'execution_id':'99:20','pgid':99,'session':99}
 assert m.validate_fault_result(before,after,99,4,birth,dict(birth))['cold_full_text_equal']
 with pytest.raises(RuntimeError):m.ordinary_binding({'api':{'uid':1}})
 with pytest.raises(RuntimeError):m.ordinary_binding({'schema':'ft_t06_ordinary_binding/v3','verdict':'worker_input_uid_token_bound','api':{'uid':1},'token_sidecar':{'events':[{'next_token':None}]}})
 with pytest.raises(RuntimeError):m.validate_fault_result(before,m.ordinary_binding(ordinary_fixture(tmp_path,4,(9,))),99,4,birth,birth)
 with pytest.raises(RuntimeError):m.validate_fault_result(before,after,99,4,birth,{**birth,'start_ticks':21})

def test_r061_controller_reserves_once_and_child_receipt_precedes_body(tmp_path,monkeypatch):
 m=load('r061_launch','r061_oom_fault_prepare_v1.py');wt=tmp_path/'candidate';wt.mkdir(); inputs=[]
 for name in ('reference','affected','queued'):
  path=tmp_path/(name+'.json');path.write_text('{}');inputs.append(path)
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'ROUNDS',tmp_path/'rounds');seen=[]
 class Owned:
  def verified_module(self,*_):return SimpleNamespace(next_batch=lambda _:81)
  def reserve_process(self,*args):
   path=args[4];value={**args[5],'state':'launched','batch_pid':333};path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));seen.append('reserve');return value
  def process_identity(self,pid):return {'pid':pid,'start_ticks':44}
  def publish_receipt(self,*args):seen.append('publish')
 def publish(path,value,child,*,lifecycle):lifecycle.publish_receipt(path,(1,1),{**value,'child':child});return {**value,'child':child}
 d=SimpleNamespace(LOCK=tmp_path/'lock',ATOMIC_HELPER_SHA='x',argv_sha256=lambda _: 'argv',process_birth=lambda:{'pid':1,'start_ticks':2,'execution_id':'1:2'},load_owned_lifecycle=lambda:Owned(),publish_child_binding=publish)
 fake_r=SimpleNamespace(candidate_binding=lambda *a:None,load_d07=lambda *a:d)
 monkeypatch.setattr(m,'r060',lambda:fake_r);monkeypatch.setattr(m,'admission',lambda *a:{} )
 dry,tmp_review=tmp_path/'dry.json',tmp_path/'review.json';dry.write_text('{}');tmp_review.write_text('{}')
 result=m.controller('f'*40,wt,*inputs,dry,tmp_review)
 assert result['child']['pid']==333 and seen==['reserve','publish']
 d.require_child_receipt=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('bad receipt'))
 with pytest.raises(RuntimeError,match='bad receipt'):m.child(81,tmp_path/'r','f'*40,wt,*inputs,dry,tmp_review)


def test_r061_admission_rejects_writable_or_mismatched_receipts_before_reserve(tmp_path, monkeypatch):
 m=load('r061_admission','r061_oom_fault_prepare_v1.py'); wt=tmp_path/'wt'; (wt/'python/freetoken/server').mkdir(parents=True); (wt/'python/freetoken/scheduler').mkdir(parents=True); (wt/'python/freetoken/engine').mkdir(parents=True)
 for rel,text in {'api_server.py':'maintenance_state = "restarting"\nbackend_epoch += 1\n','supervisor.py':'restart_backend\nmax_restarts\n','engine.py':'def forward_batch(): pass\n'}.items(): (wt/'python/freetoken/server'/rel if rel!='engine.py' else wt/'python/freetoken/engine'/rel).write_text(text)
 (wt/'python/freetoken/scheduler/scheduler.py').write_text('FT_DEV_OOM_INJECT FT_DEV_OOM_UID FT_DEV_OOM_POINT before_forward _dev_oom_used torch.cuda.OutOfMemoryError')
 monkeypatch.setattr(m,'r060',lambda:SimpleNamespace(candidate_binding=lambda *_:{}))
 dry=tmp_path/'dry.json'; review=tmp_path/'review.json'; doc={'rid':m.RID,'candidate_commit':'a'*40,'source_sha256':{}}
 dry.write_text(json.dumps(doc));review.write_text(json.dumps(doc))
 if os.name=='nt':
  with pytest.raises(RuntimeError): m.admission('a'*40,wt,dry,review)
  return
 dry.chmod(0o444);review.chmod(0o444)
 assert m.admission('a'*40,wt,dry,review)['file_dry']['path']==str(dry)
 review.chmod(0o644)
 with pytest.raises(RuntimeError): m.admission('a'*40,wt,dry,review)


def test_r060_native_provenance_requires_parent_symlink_and_candidate_regular_copy(tmp_path, monkeypatch):
 m=load('r060_native','r060_oom_t16_prepare_v1.py'); proof=tmp_path/'native.json'
 doc={'schema':'ft_r060_oom_native_provenance/v1','candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'candidate_worktree':'/data2/FreeToken/wt/e2oom-recovery','parent_worktree':'/data2/FreeToken/wt/e2base1-ordinary-rewind','native_sources_unchanged':True,'native':{name:{'regular_copy':True,'parent_is_symlink':True,'parent_resolved_path':'/data2/FreeToken/wt/e2base/python/freetoken/kernel/x.so','size':1,'sha256':'a'*64} for name in ('_cpu_moe','_pinned_tensor')}}
 proof.write_text(json.dumps(doc)); monkeypatch.setattr(m,'NATIVE_PROVENANCE',proof);monkeypatch.setattr(m,'NATIVE_PROVENANCE_SHA256',m.sha(proof))
 if os.name=='nt':
  with pytest.raises(RuntimeError):m.require_r060_native_provenance()
  return
 proof.chmod(0o444)
 assert m.require_r060_native_provenance()['candidate_commit']==m.CANDIDATE
 proof.chmod(0o644);proof.write_text(json.dumps({**doc,'native_sources_unchanged':False}));proof.chmod(0o444);monkeypatch.setattr(m,'NATIVE_PROVENANCE_SHA256',m.sha(proof))
 with pytest.raises(RuntimeError):m.require_r060_native_provenance()
