import importlib.util,json,types
from pathlib import Path
import pytest

P=Path(__file__).parents[1]/"r046_d07_t06_prepare.py";s=importlib.util.spec_from_file_location("r046",P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
ORIGINAL_T20_PRECONDITION=m.require_t20_terminal_decision

@pytest.fixture(autouse=True)
def fake_formal_review_for_existing_lifecycle_tests(monkeypatch):
 monkeypatch.setattr(m,'require_output_root',lambda *_:None)
 monkeypatch.setattr(m,'require_startup_review',lambda:{'path':'review','sha256':'bound'})
 monkeypatch.setattr(m,'require_t20_terminal_decision',lambda:m.load_d07().require_t20_kept())

def test_user_decision_preserves_failed_evidence_without_requiring_kept(tmp_path):
 rounds=tmp_path/'rounds';directory=rounds/'E2-R040';directory.mkdir(parents=True)
 status={'state':'failed','batch_pid':3576643,'rid':'E2-R040','batch':71}
 (directory/'status_batch71.json').write_text(json.dumps(status));(directory/'failed_harness.json').write_text('{"admitted":false}')
 hashes={str(p):m.sha(p) for p in directory.iterdir()}
 receipt=tmp_path/'receipt.json';receipt.write_text(json.dumps({'schema':'ft_t20_batch71_failed_terminal_observation/v1','rid':'E2-R040','batch':71,'state':'failed_harness_pending_D04','round_tree_readonly':True,'controller_absent':True,'files_sha256':hashes}))
 for p in (receipt,*directory.iterdir()):p.chmod(0o444)
 directory.chmod(0o555)
 digest=m.sha(receipt)
 assert ORIGINAL_T20_PRECONDITION(receipt,rounds,digest)==receipt
 (directory/'status_batch71.json').chmod(0o644)
 with pytest.raises(RuntimeError,match='evidence changed'):ORIGINAL_T20_PRECONDITION(receipt,rounds,digest)

def test_user_decision_rejects_changed_terminal_receipt(tmp_path):
 p=tmp_path/'receipt.json';p.write_text('{}');p.chmod(0o444)
 with pytest.raises(RuntimeError,match='changed'):ORIGINAL_T20_PRECONDITION(p,tmp_path,'0'*64)

def test_actual_pinned_protocol_exposes_birth_reader_and_cleans_real_process():
 import os,sys,subprocess
 if sys.platform!='linux':pytest.skip('actual pinned Linux lifecycle')
 d=m.load_d07()
 if not (d.OWNED_SOURCE/'t17_owned_launch_protocol.py').exists():pytest.skip('server frozen protocol only')
 owned=d.load_owned_lifecycle()
 mine=owned.process_identity(os.getpid())
 assert mine['pid']==os.getpid() and mine['start_ticks']>0 and mine['pgid']==os.getpgid(0)
 process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(2)'],start_new_session=True)
 try:
  child=owned.process_identity(process.pid)
  assert child['pgid']==child['session']==process.pid and child['start_ticks']>0
 finally:owned.stop_owned_process(process)
 assert not owned.owned_group_alive(process.pid)

def test_controller_does_not_reserve_batch_while_foreign_gpu_lock_exists(monkeypatch,tmp_path):
 d=m.load_d07();proof=tmp_path/'proof.json';proof.write_text('{}')
 lock=tmp_path/'gpu.lock';lock.write_text('foreign owner')
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'load_d07',lambda:d)
 monkeypatch.setattr(m,'packet',lambda _:{});
 monkeypatch.setattr(d,'require_r041_kept',lambda _:proof);monkeypatch.setattr(d,'require_t20_kept',lambda:proof)
 monkeypatch.setattr(d,'LOCK',lock)
 monkeypatch.setattr(d,'load_owned_lifecycle',lambda:pytest.fail('foreign lock must prevent any batch reservation'))
 with pytest.raises(RuntimeError,match='foreign GPU lock'):
  m.execute(tmp_path/'wt',tmp_path/'rounds')
 assert lock.read_text()=='foreign owner'


def test_controller_reserves_once_and_normalizes_real_child_identity(monkeypatch,tmp_path):
 d=m.load_d07();proof=tmp_path/'proof.json';proof.write_text('{}');seen={}
 monkeypatch.setattr(d,'LOCK',tmp_path/'absent-gpu.lock')
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'ROOT',tmp_path/'root')
 monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{})
 
 monkeypatch.setattr(d,'require_r041_kept',lambda _:proof);monkeypatch.setattr(d,'require_t20_kept',lambda:proof)
 monkeypatch.setattr(d,'take_d07_gpu_lock',lambda *a:pytest.fail('controller must not take GPU lock'))
 monkeypatch.setattr(d,'process_birth',lambda:{'pid':111,'start_ticks':99,'execution_id':'111:99'})
 def reserve(helper,batch,rid,argv,path,packet):
  assert batch==77 and rid==m.RID and path.parent.is_dir() and 'batch77' in path.name
  receipt={**packet,'state':'launched','batch_pid':222};path.write_text(json.dumps(receipt));return receipt
 def publish(path,identity,value):
  assert value['child']=={'pid':222,'start_ticks':123,'execution_id':'222:123'}
  assert (path.stat().st_dev,path.stat().st_ino)==identity
  seen['value']=value
 owned=types.SimpleNamespace(verified_module=lambda *a:types.SimpleNamespace(next_batch=lambda _:77),reserve_process=reserve,process_identity=lambda _: {'pid':222,'start_ticks':123,'pgid':222,'session':222},publish_receipt=publish)
 monkeypatch.setattr(d,'load_owned_lifecycle',lambda:owned)
 assert m.execute(tmp_path/'wt',tmp_path/'rounds')==seen['value']

def test_cpu_fixture_socket_guard_is_ephemeral_and_packet_declares_cuda_hidden(monkeypatch,tmp_path):
 source=P.with_name("d07_g3g4_prepare.py");spec=importlib.util.spec_from_file_location("r046_d07_socket",source);d07=importlib.util.module_from_spec(spec);spec.loader.exec_module(d07)
 port=d07.dynamic_fixture_port();assert 1024 <= port <= 65535 and port != 8095
 class D:
  def checked_worktree(self,_): return {"tracked_clean":True}
  def verify_d07_tools(self,_): return {"tools":True}
  def dynamic_fixture_port(self): return port
 monkeypatch.setattr(m,"load_d07",lambda:D());monkeypatch.setattr(m,"seed_paths",lambda:{role:tmp_path/f"{role}.txt" for role in m.SEEDS})
 for path in m.seed_paths().values(): path.write_text("seed")
 packet=m.packet(tmp_path);assert packet["fixture_port"]==port and packet["cuda_visible_devices_cpu_guard"]==""

def test_g3g4_runs_before_t06_arms_and_binds_real_artifacts(tmp_path):
 calls=[]
 class D:
  def dynamic_fixture_port(self): return 43000+len(calls)
  def start_server(self,directory,_wt,_port,route):
   (directory/'serve.log').write_text('CUDA graph disabled for development route trace' if route else 'ordinary');calls.append(('start',directory.name));return object()
  def load_owned_lifecycle(self): return types.SimpleNamespace(stop_owned_process=lambda _:calls.append(('stop',None)))
  def invoke_cold_eq(self,_wt,_port,cold_id,out):out.write_text(json.dumps({'text':'same','record':{'cold_id':cold_id,'finish_reason':'stop','built_tokens':32052,'completion_tokens':1}}))
  def invoke_agent_trace(self,_wt,_port,out):out.write_text('{}')
  def invoke_analyzer(self,_wt,_route,_trace,_serve,out):out.write_text(json.dumps({'suffix_tokens':[{'uid':1}],'business_uids':[1]}))
  def g3_compare(self,off,on):return {'byte_identical':json.loads(off.read_text())['text']==json.loads(on.read_text())['text']}
 (tmp_path/'run').mkdir();got=m.run_g3g4(D(),tmp_path,tmp_path/'run')
 assert calls==[('start','g3_off'),('stop',None),('start','g3_on'),('stop',None)]
 assert got['g3']['byte_identical'] and got['g4']['business_uids']==1 and (tmp_path/'run'/'g3g4'/'route_summary.json').is_file()

def test_live_owned_group_preserves_gpu_lock_and_records_cleanup(monkeypatch,tmp_path):
 released=[];proc=types.SimpleNamespace(pid=88)
 class D:
  def require_r041_kept(self,_):p=tmp_path/'r';p.write_text('{}');return p
  def require_t20_kept(self):return tmp_path/'r'
  def take_d07_gpu_lock(self,*_):return {'owner':'R046'}
  def release_d07_gpu_lock(self,_):released.append(True)
  def require_gpu_idle(self):return [0]
  def dynamic_fixture_port(self):return 43001
  def start_server(self,*_):return proc
  def load_owned_lifecycle(self):return types.SimpleNamespace(stop_owned_process=lambda _:None,owned_group_alive=lambda _:True)
  def write_new(self,p,v):m.write_new(p,v)
 d=D();wt=tmp_path/'wt';(wt/'scripts').mkdir(parents=True)
 monkeypatch.setattr(m.sys,'platform','linux')
 monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{})
 monkeypatch.setattr(m,'seed_paths',lambda:{role:tmp_path/f'{role}.txt' for role in m.SEEDS})
 for p in m.seed_paths().values():p.write_text('s')
 monkeypatch.setattr(m,'run_g3g4',lambda *_:{})
 monkeypatch.setattr(m,'require_receipt',lambda *_:{})
 monkeypatch.setattr(m,'invoke_seed',lambda *_:(_ for _ in ()).throw(RuntimeError('client fail')))
 with pytest.raises(RuntimeError,match='preserve GPU lock'):m.execute(wt,tmp_path/'rounds',owned_child=True,batch=9,launch_receipt=tmp_path/'x')
 cleanup=json.loads((tmp_path/'rounds'/m.RID/'owned_cleanup.json').read_text());assert cleanup['lock_released'] is False and not released

def test_g3g4_start_cleanup_failure_propagates_original_process(monkeypatch,tmp_path):
 proc=types.SimpleNamespace(pid=88)
 def start(*args):
  error=RuntimeError('start failed');error.owned_process=proc;raise error
 def stop(p):
  assert p is proc
  raise RuntimeError('G3 stop failed')
 d=types.SimpleNamespace(dynamic_fixture_port=lambda:43001,start_server=start,load_owned_lifecycle=lambda:types.SimpleNamespace(stop_owned_process=stop))
 with pytest.raises(RuntimeError,match='G3 stop failed') as caught:m.run_g3g4(d,tmp_path,tmp_path)
 assert caught.value.owned_process is proc and caught.value.owned_cleanup_failed

def test_g3g4_cleanup_failure_preserves_outer_lock(monkeypatch,tmp_path):
 proc=types.SimpleNamespace(pid=88);proof=tmp_path/'proof';proof.write_text('{}');released=[]
 d=types.SimpleNamespace(require_r041_kept=lambda _:proof,require_t20_kept=lambda:proof,take_d07_gpu_lock=lambda *a:{'owner':m.RID},release_d07_gpu_lock=lambda _:released.append(True),require_gpu_idle=lambda:[0],load_owned_lifecycle=lambda:types.SimpleNamespace(owned_group_alive=lambda _:False))
 d.write_new=m.write_new
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{});monkeypatch.setattr(m,'require_receipt',lambda *a:{})
 def fail(*args):
  error=RuntimeError('G3 stop failed');error.owned_process=proc;error.owned_cleanup_failed=True;raise error
 monkeypatch.setattr(m,'run_g3g4',fail)
 with pytest.raises(RuntimeError,match='preserve GPU lock'):m.execute(tmp_path,tmp_path/'rounds',owned_child=True,batch=9,launch_receipt=proof)
 assert not released and json.loads((tmp_path/'rounds'/m.RID/'owned_cleanup.json').read_text())['lock_released'] is False

def test_manifest_requires_four_independent_arms_and_seed12k_training_only(tmp_path):
 arms=[{"role":x,"directory":f"G_{x}","kind":"generate","rounds":12,"max_tokens":2048,"seed_raw_sha256":m.SEEDS[x]} for x in m.SEEDS]+[{"role":"two","directory":"G_two","kind":"two-decode","same_prompt":False,"ctx":8000,"max_tokens":256}]
 doc={"schema":"ft_r046_route_manifest/v1","rid":m.RID,"candidate_commit":m.CANDIDATE,"arms":arms,"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"]}
 (tmp_path/"manifest.json").write_text(json.dumps(doc));assert m.validate_manifest(tmp_path)["arms"][-1]["role"]=="two"
 doc["d15_training_route"]="G_seed_real/route";(tmp_path/"manifest.json").write_text(json.dumps(doc))
 with pytest.raises(ValueError,match="training/heldout"):m.validate_manifest(tmp_path)

def test_execute_four_serial_services_raw_manifest_and_d06_hash_consumer(monkeypatch,tmp_path):
 order=[]; worktree=tmp_path/'wt';(worktree/'scripts').mkdir(parents=True)
 for name in ('agent_trace.py','route_analyze.py','multisession_probe.py'):(worktree/'scripts'/name).write_text('')
 class D:
  ATOMIC_HELPER_SHA='pin'
  def write_new(self,p,d): m.write_new(p,d)
  def require_r041_kept(self,_): p=tmp_path/'r041.json';p.write_text('{}');return p
  def require_t20_kept(self): p=tmp_path/'t20.json';p.write_text('{}');return p
  def require_gpu_idle(self): order.append('idle');return [0]
  def take_d07_gpu_lock(self,r,b): order.append('lock');return {'owner':r,'batch':b}
  def release_d07_gpu_lock(self,o): order.append('unlock')
  def dynamic_fixture_port(self): return 43123+len(order)
  def load_owned_lifecycle(self): return types.SimpleNamespace(verified_module=lambda *_:pytest.fail('child must not allocate another batch'),stop_owned_process=lambda _:order.append('stop'))
  def start_server(self,g,wt,port,route): (g/'serve.log').write_text(f'started {port}');(route/'one').write_text('r');order.append('start');return object()
 d=D();monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{'schema':'preflight'})
 r041=tmp_path/'r041';t20=tmp_path/'t20';r041.write_text('x');t20.write_text('y');
 seeds={}
 for role in m.SEEDS: p=tmp_path/f'{role}.txt';p.write_text(role);seeds[role]=p
 monkeypatch.setattr(m,'seed_paths',lambda:seeds)
 def seed(_wt,_port,role,_seed,out,log): out.write_text('{}');out.with_suffix('.seed_binding.json').write_text(json.dumps({'seed_raw_sha256':m.SEEDS[role],'actual_wire_first_content_sha256':'x'}));log.write_text('ok')
 monkeypatch.setattr(m,'invoke_seed',seed);monkeypatch.setattr(m,'invoke_two',lambda _wt,_p,out,log:(out.write_text(json.dumps({'same_prompt':False})),log.write_text('ok')))
 def analyze(_wt,_g,out,**kwargs):
  if kwargs.get("trace") is not None:
   out.write_text(json.dumps({"analysis_scope":"trace_bound_business_requests","suffix_tokens":[{"uid":n,"n":1} for n in range(12)],"business_uids":list(range(12)),"missing_business_routes":[],"completion_count":12,"completions":{str(n):{"max_tokens":2048} for n in range(12)}},sort_keys=True))
  else:
   out.write_text(json.dumps({"analysis_scope":"all_prefill_requests","raw_suffix_tokens":{"1":1,"2":1},"business_uids":[],"two_decode_pairs":[{"uids":[1,2]}],"two_decode_pair_steps":{"pair":0},"R_B_pending":True,"R_B":{},"R_B_nullreason":"declared two-decode pair evidence or overlapping decode routes unavailable"},sort_keys=True))
 monkeypatch.setattr(m,'invoke_analysis',analyze);monkeypatch.setattr(m.sys,'platform','linux')
 monkeypatch.setattr(m,'run_g3g4',lambda *_:{"schema":"ft_r046_g3g4_raw/v1","directory":"g3g4","g3":{"byte_identical":True},"g4":{"route_summary":"g3g4/route_summary.json","route_summary_sha256":"x","business_uids":2,"suffix_tokens":2},"cuda_graph_disabled_marker":True})
 monkeypatch.setattr(m,'require_receipt',lambda *_: {})
 result=m.execute(worktree,tmp_path/'rounds',owned_child=True,batch=77,launch_receipt=tmp_path/'launch.json');run=tmp_path/'rounds'/m.RID
 assert result['verdict']=='pending_review' and result['proposed_verdict']=='measured'
 assert result['base']=={'code_version':'E2-base.1@0aa23431','commit':m.CANDIDATE}
 assert all((run/f'G_{role}'/'route').is_dir() for role in (*m.SEEDS,'two'))
 assert order==['lock','idle','start','stop','start','stop','start','stop','start','stop','unlock']
 assert not (run/'round.json').exists() and not (run/'MANIFEST.sha256').exists()
 evidence=json.loads((run/'manifest.json').read_text());assert evidence['g3g4']['g3']['byte_identical'] and evidence['service']['independent_arms'][0]=='g3g4'
 assert evidence['d15_training_route']=='G_seed12k/route' and 'G_seed_real/route' in evidence['heldout_routes']
 seed12=next(arm for arm in evidence["arms"] if arm["role"]=="seed12k")
 heldout=next(arm for arm in evidence["arms"] if arm["role"]=="seed_real")
 for key in ("serve_log","trace","seed_binding","route_summary"):
  seed12[key]=heldout[key];seed12[key+"_sha256"]=heldout[key+"_sha256"];evidence["files"][f"seed12k_{key}"]={"path":heldout[key],"sha256":heldout[key+"_sha256"]}
 assert evidence['arms'][0]['serve_log']==heldout['serve_log']
 evidence=json.loads((run/'manifest.json').read_text())
 (run/'G_seed_real'/'serve.log').write_text('tampered')
 assert (run/'G_seed_real'/'serve.log').read_text()=='tampered'

def test_invoke_analysis_accepts_empty_two_business_uids_but_rejects_seed_missing_uid(monkeypatch,tmp_path):
 class D:
  def clean_environment(self,_): return {}
 monkeypatch.setattr(m,"load_d07",lambda:D())
 def fake_run(cmd,**_kwargs):
  out=Path(cmd[cmd.index("--out")+1])
  if "--traces" in cmd:
   out.write_text(json.dumps({"analysis_scope":"trace_bound_business_requests","suffix_tokens":[{"uid":n,"n":1} for n in range(12)],"business_uids":list(range(12)),"missing_business_routes":[],"completion_count":12,"completions":{str(n):{"max_tokens":2048} for n in range(12)}}))
  else:
   assert "--traces" not in cmd
   out.write_text(json.dumps({"analysis_scope":"all_prefill_requests","raw_suffix_tokens":{"1":1,"2":1},"business_uids":[],"two_decode_pairs":[{"uids":[1,2]}],"two_decode_pair_steps":{"pair":0},"R_B_pending":True,"R_B":{},"R_B_nullreason":"declared two-decode pair evidence or overlapping decode routes unavailable"}))
 monkeypatch.setattr(m.subprocess,"run",fake_run)
 g=tmp_path/"G_seed";g.mkdir();(g/"route").mkdir();(g/"serve.log").write_text("log");trace=g/"trace.json";trace.write_text("trace")
 m.invoke_analysis(tmp_path,g,tmp_path/"seed.json",trace=trace)
 two_g=tmp_path/"G_two";two_g.mkdir();(two_g/"route").mkdir();(two_g/"serve.log").write_text("log");two=two_g/"two.json";two.write_text("two")
 m.invoke_analysis(tmp_path,two_g,tmp_path/"two.json.out",two=two)
 def missing_uid(cmd,**_kwargs):
  out=Path(cmd[cmd.index("--out")+1]);out.write_text(json.dumps({"analysis_scope":"trace_bound_business_requests","suffix_tokens":[{"uid":1,"n":1}],"business_uids":[],"missing_business_routes":[],"completion_count":12,"completions":{str(n):{"max_tokens":2048} for n in range(12)}}))
 monkeypatch.setattr(m.subprocess,"run",missing_uid)
 (g/"route_analyze.log").unlink()
 with pytest.raises(RuntimeError,match="UID-bound"):
  m.invoke_analysis(tmp_path,g,tmp_path/"bad.json",trace=trace)


def test_canonical_paths_reject_arbitrary_output(monkeypatch,tmp_path):
 spec=importlib.util.spec_from_file_location('r046_paths',P);actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
 with pytest.raises(RuntimeError,match='canonical'):actual.require_output_root(actual.WT,tmp_path)

def test_review_rejects_writable_and_changed_sources(monkeypatch,tmp_path):
 spec=importlib.util.spec_from_file_location('r046_review',P);actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
 directory=tmp_path/'review';directory.mkdir();monkeypatch.setattr(actual,'REVIEW_DIR',directory)
 (directory/'review.json').write_text('{}');(directory/'pin.json').write_text('{}')
 with pytest.raises(RuntimeError,match='writable'):actual.require_startup_review()


def test_review_accepts_exact_runtime_binding_and_rejects_tamper(monkeypatch,tmp_path):
 import os
 spec=importlib.util.spec_from_file_location('r046_bound_review',P);actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
 root=tmp_path/'root';wt=tmp_path/'wt';directory=tmp_path/'review';directory.mkdir()
 monkeypatch.setattr(actual,'ROOT',root);monkeypatch.setattr(actual,'WT',wt);monkeypatch.setattr(actual,'REVIEW_DIR',directory)
 monkeypatch.setattr(actual,'D07_SOURCE',root/'d07.py');monkeypatch.setattr(actual,'SEED_CLIENT',root/'seed.py')
 paths=[actual.D07_SOURCE,actual.SEED_CLIENT,root/'runs/plan_batches/e2_launch.py',*[wt/'scripts'/n for n in ('agent_trace.py','_agent_trace_original.py','route_analyze.py','multisession_probe.py')]]
 for path in paths:path.parent.mkdir(parents=True,exist_ok=True);path.write_text('source')
 sources={str(path):actual.sha(path) for path in [P.resolve(),*paths]}
 review={'schema':'ft_r046_source_startup_review/v1','verdict':'PASS','source_execution_ready':True,'candidate_commit':actual.CANDIDATE,'sources':sources}
 (directory/'review.json').write_text(json.dumps(review));(directory/'pin.json').write_text(json.dumps({'schema':'ft_r046_review_pin/v1','rid':actual.RID,'review_sha256':actual.sha(directory/'review.json')}))
 for path in directory.iterdir():path.chmod(0o444)
 directory.chmod(0o555)
 try:
  if os.name=='nt':pytest.skip('POSIX sealed-review permissions verified by Linux stage')
  assert actual.require_startup_review()['sha256']==actual.sha(directory/'review.json')
  paths[0].write_text('changed')
  with pytest.raises(RuntimeError,match='source SHA differs'):actual.require_startup_review()
 finally:
  directory.chmod(0o755)
  for path in directory.iterdir():path.chmod(0o644)
