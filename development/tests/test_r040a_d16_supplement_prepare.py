import hashlib, importlib.util, json
from pathlib import Path
import pytest
from types import SimpleNamespace
ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('r040a_prepare',ROOT/'r040a_d16_supplement_prepare.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def write(root,name):
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name);return p
def test_prepare_binds_shutdown_wrapper_and_declares_existing_physical_capture(tmp_path):
 for n in m.REQUIRED: write(tmp_path,n)
 value=m.prepare(tmp_path)
 assert value['rid']=='E2-R040a' and value['default_action']=='inert_prepare_only'
 assert value['wrapper']['path'].endswith('d16_native_capture_shutdown_v3.py')
 assert {x['arm']:x['state'] for x in value['scope']}['parking']=='queued'
 assert value['gpu_execution_permitted'] is False
 assert all(len(v['sha256'])==64 for v in value['source_files'].values())
def test_missing_source_and_existing_output_rejected(tmp_path):
 write(tmp_path,'d16_native_capture_shutdown_v3.py')
 with pytest.raises(m.R040aPreparationError,match='missing regular'):m.prepare(tmp_path)
 for n in m.REQUIRED: write(tmp_path,n)
 output=tmp_path/'prepare.json';output.write_text('{}')
 with pytest.raises(m.R040aPreparationError,match='new regular'):m.main(['--source-root',str(tmp_path),'--write-prepare-json',str(output)])


def test_foreign_lock_rejects_before_review_or_batch(monkeypatch,tmp_path):
 lock=tmp_path/'lock';lock.write_text('other owner')
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'RUNS',tmp_path/'rounds')
 monkeypatch.setattr(m,'shared_protocol',lambda:SimpleNamespace(LOCK=lock))
 monkeypatch.setattr(m,'require_review',lambda _:pytest.fail('foreign lock must reject before source review'))
 with pytest.raises(m.R040aPreparationError,match='foreign GPU lock'):m.execute()


def test_controller_uses_actual_reservation_and_birth_binding(monkeypatch,tmp_path):
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'RUNS',tmp_path/'rounds')
 calls=[]
 class Lifecycle:
  def verified_module(self,*_):return SimpleNamespace(next_batch=lambda _:91)
  def reserve_process(self,allocator,batch,rid,argv,path,reserved):
   calls.append((batch,rid,argv,path,reserved));return {**reserved,'batch_pid':123}
  def process_identity(self,_):return {'pid':123,'start_ticks':45,'execution_id':'123:45','pgid':123}
 lifecycle=Lifecycle()
 d=SimpleNamespace(LOCK=tmp_path/'lock',ATOMIC_HELPER_SHA='pin',load_owned_lifecycle=lambda:lifecycle,
      argv_sha256=lambda _:'sha',process_birth=lambda:{'pid':10,'start_ticks':20},
      publish_child_binding=lambda p,r,c,**_: {**r,'child':c})
 monkeypatch.setattr(m,'shared_protocol',lambda:d);monkeypatch.setattr(m,'require_review',lambda _:{})
 value=m.execute(after='E2-R046')
 assert value['child']=={'pid':123,'start_ticks':45,'execution_id':'123:45'}
 assert calls[0][0:2]==(91,m.RID) and '--owned-child' in calls[0][2]


def test_child_preserves_lock_after_uncertain_stop(monkeypatch,tmp_path):
 (tmp_path/'rounds').mkdir()
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'RUNS',tmp_path/'rounds')
 review_dir=tmp_path/'review';review_dir.mkdir();(review_dir/'review.json').write_text('{}');monkeypatch.setattr(m,'REVIEW_DIR',review_dir)
 inputs=tmp_path/'inputs';inputs.write_text('{}')
 monkeypatch.setattr(m,'require_review',lambda _:{'input_binding':{'path':str(inputs),'sha256':m.sha(inputs)},'collector_review':'review','collector_review_sha256':'sha'})
 class Owner:
  proc=object()
  def set_status(self,**_):pass
  def stop(self):raise RuntimeError('stop failed')
 d=SimpleNamespace(require_child_receipt=lambda *_,**__:None,take_d07_gpu_lock=lambda *_:{'owner':m.RID},
                   require_gpu_idle=lambda:None,release_d07_gpu_lock=lambda _:pytest.fail('must preserve uncertain lock'))
 monkeypatch.setattr(m,'shared_protocol',lambda:d);monkeypatch.setattr(m,'create_service_owner',lambda *_:Owner())
 monkeypatch.setattr(m,'invoke_owned_supplement',lambda *_,**__: (_ for _ in ()).throw(RuntimeError('collection failed')))
 with pytest.raises(m.R040aPreparationError,match='preserve GPU lock'):m.execute(owned_child=True,batch=91,receipt=tmp_path/'receipt')
 assert json.loads((tmp_path/'rounds'/m.RID/'owned_cleanup.json').read_text())['lock_released'] is False


def test_supplement_calls_only_five_d16_arms_and_never_baseline():
    class Native:
        def __init__(self): self.calls=[]
        def collect_native_processes(self,*args,**kw): self.calls.append(('native',kw['slots'],kw.get('interleave',False),len(args[1])));return {'kind':'native'}
        def collect_parking_processes(self,*args,**kw): self.calls.append(('parking',));return {'kind':'parking'}
        def collect_cache_processes(self,*args,**kw): self.calls.append(('cache',));return {'kind':'cache'}
    cases=[{'name':f's{i}','query':[i]*512,'input_ids_sha256':str(i)} for i in range(4)]
    cases.append({'name':'long','query':[9]*5000,'input_ids_sha256':'long'})
    native=Native(); result,proof=m.run_supplement_body(object(),{'cases':cases},'wrapper','review','sha',native_module=native)
    assert native.calls==[('native',2,False,2),('native',4,False,4),('parking',),('cache',),('native',2,True,2)]
    assert len(proof['short'])==4 and result['anchor_four_cell'].startswith('not_executed')


def test_owner_factory_uses_real_run_shape_and_rejects_wrong_owner():
    from types import SimpleNamespace
    class Run:
     def __init__(self,options,**kw): self.options=options
     def service(self): pass
     def environment(self): pass
    owner=m.make_owned_owner(SimpleNamespace(rid='E2-R040a',gate='T20',run=True),gpu_module=SimpleNamespace(Run=Run))
    assert owner.options.rid=='E2-R040a'


def test_candidate_runtime_uses_0aa_worktree_before_run_construction(tmp_path):
 from types import SimpleNamespace
 gpu=SimpleNamespace(helper=SimpleNamespace())
 old=SimpleNamespace(_imports=lambda:(gpu,object()))
 candidate={'worktree':str(tmp_path),'parent_commit':'0aa-parent','candidate_commit':'0aa23431'}
 got,_=m.configure_candidate_runtime(old,candidate)
 assert str(got.WT)==str(tmp_path) and got.helper.CANDIDATE=='0aa23431' and old.PARENT=='0aa-parent'
