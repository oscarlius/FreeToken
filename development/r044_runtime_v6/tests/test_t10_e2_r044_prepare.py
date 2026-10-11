import importlib.util,json,sys,types
from pathlib import Path
import pytest
P=Path(__file__).parents[1]/"r044_prepare_v6.py";s=importlib.util.spec_from_file_location("t10",P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
W=Path(__file__).parents[1]/"t10_capture_startup.py";s=importlib.util.spec_from_file_location("t10_capture",W);w=importlib.util.module_from_spec(s);s.loader.exec_module(w)

def test_queue_retains_failed_T11_and_requires_successor_and_T20_completion(tmp_path):
 calls=[]
 class Gate:
  LOCK=tmp_path/'gpu.lock'
  def require_t20_failed_harness(self):calls.append(('E2-R040','failed_harness'));return tmp_path/'t20.json'
  def require_closed_round(self,rid,verdict):calls.append((rid,verdict));return tmp_path/rid/'round.json'
 m.require_queue(Gate())
 assert calls==[('E2-R040','failed_harness'),('E2-R052','failed_harness'),('E2-R052a','measured'),('E2-R040f','measured')]

@pytest.mark.parametrize('missing',['E2-R052a','E2-R040f'])
def test_queue_rejects_missing_actual_completion_before_any_launch(tmp_path,missing):
 class Gate:
  LOCK=tmp_path/'gpu.lock'
  def require_t20_failed_harness(self):return tmp_path/'t20.json'
  def require_closed_round(self,rid,verdict):
   if rid==missing:raise RuntimeError('missing measured prerequisite')
 with pytest.raises(RuntimeError,match='missing measured prerequisite'):m.require_queue(Gate())
def test_first_records_fulltext_token_count_and_uid_cache():
 a={"text":"same","completion_tokens":4,"uid":9,"cached_tokens":0,"sampled_token_ids":[1,2,3,4],"capture_input_receipt_sha256":"a"};b={**a,"cached_tokens":8};row=m.first(a,b)
 assert row["same_fulltext"] and row["same_sampled_token_ids"] and row["left_uid_cached_tokens"]=={"uid":9,"cached_tokens":0}

def test_file_dry_writes_all_service_plans_without_launch(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'packet',lambda _:{'checked':True});monkeypatch.setattr(m,'ROUNDS',tmp_path/'formal')
 monkeypatch.setattr(m,'require_queue',lambda _:None)
 monkeypatch.setattr(m,'startup_source_hashes',lambda:{'actual':'source'})
 monkeypatch.setattr(m.os,'getuid',lambda:1000,raising=False)
 class D:
  def serve_argv(self,port):return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--prefill-layer-major']
  def clean_environment(self,*_,**__):return {'PYTHONPATH':'candidate/python','CUDA_VISIBLE_DEVICES':'0'}
 monkeypatch.setattr(m,'load_d07',lambda:D())
 dry=tmp_path/'formal'/'.dryrun_R044_cpu'
 monkeypatch.setattr(m.subprocess,'Popen',lambda *_a,**_k:pytest.fail('file dry started service'))
 value=m.file_dry_run(dry)
 assert value['service_started'] is False and len(value['services'])==6
 assert all((dry/row['mode']/row['arm']/'service_plan.json').is_file() for row in value['services'])
 assert all(item['port_pair']['tcpstore']==item['port_pair']['api']+1 for item in value['services'])
 assert m.require_file_dry_receipt(dry/'dry_run_receipt.json')['sha256']==m.sha(dry/'dry_run_receipt.json')
 for row in value['services']:
  plan=json.loads((dry/row['mode']/row['arm']/'service_plan.json').read_text())
  assert Path(plan['argv'][2]).is_file() and 'serve' in plan['argv']
  assert '--kv-reserve-tokens' in plan['argv'] and '98304' in plan['argv']
  assert plan['pause'] is False and plan['route_trace'] is False
 for p in dry.rglob('*'):
  if p.is_file():p.chmod(0o600)
def test_capture_binding_requires_actual_sequential_uid_and_full_token_count():
 replay={"a":{"uid":0,"completion_tokens":2}}
 capture={"sampler_root":"/captured","uids":{"0":{"input_ids_sha256":"receipt","sampled_token_ids":[7,8]}}}
 assert m.bind_capture(replay,capture,0)["a"]["sampled_token_ids"]==[7,8]
 with pytest.raises(ValueError):m.bind_capture(replay,{"sampler_root":"/captured","uids":{"0":{"input_ids_sha256":"receipt","sampled_token_ids":[7]}}},0)
def test_start_mode_uses_existing_service_capture_startup_and_declares_all_http_uids(monkeypatch,tmp_path):
 class D:
  def serve_argv(self,port):return ["ft","serve","--port",str(port),"--kv-reserve-tokens","49152","--max-seq-len-override","49152","--prefill-layer-major"]
  def clean_environment(self,*_,trace_dir=None):
   assert trace_dir is None
   return {"PYTHONPATH":"candidate/python"}
 d=D();m.start_mode(d,tmp_path/"B1",tmp_path/"wt",41411,tmp_path/"route",False,file_dry=True)
 seen=json.loads((tmp_path/'B1'/'service_plan.json').read_text());seen['env']=seen['environment']
 assert seen["argv"][:4]==[str(m.VENV/"bin/python"),"-u",str(m.CAPTURE_STARTUP),'serve'] and "--prefill-layer-major" not in seen["argv"]
 assert seen["env"]["FT_D16_SERVICE_CAPTURE_EXPECTED_JSON"].endswith("expected_capture.json") and seen["env"]["PYTHONPATH"].endswith(str(tmp_path/"wt"/"scripts"))
 assert not {'FT_DEV_ROUTE_TRACE','FT_DEV_PAUSE_ENDPOINT'} & seen['env'].keys()
 assert len(json.loads((tmp_path/"B1"/"expected_capture.json").read_text()))==m.CAPTURE_REQUESTS*m.CAPTURE_MAX_TOKENS
def test_terminal_cap_accepts_real_early_finish_and_rejects_missing_extra_or_nonterminal(monkeypatch):
 monkeypatch.setenv("FT_T10_CAPTURE_MAX_TOKENS","200")
 class Registry:
  def __init__(self):self.rows={0:{"sampled_tokens":[1,2,3]},1:{"sampled_tokens":[4,5,6]}}
  def get(self,uid):return self.rows[uid]
 def adapter(rows):
  value=types.SimpleNamespace(_expected_by_uid={0:[{"generation_index":n} for n in range(200)],1:[{"generation_index":n} for n in range(200)]},deliveries=rows,registry=Registry())
  value._report=lambda terminal,error,extras:{"terminal":terminal}
  return w.install_terminal_cap(value)
 good=[{"uid":0,"generation_index":n,"finished":n==2} for n in range(3)]+[{"uid":1,"generation_index":n,"finished":n==2} for n in range(3)]
 value=adapter(good);assert value._delivery_extras()==[] and len(value._expected_by_uid[0])==3 and value._report("complete",None,[])["t10_terminal_cap"]["actual_delivery_counts"]=={"0":3,"1":3}
 with pytest.raises(ValueError):adapter(good[:3])._delivery_extras()
 bad=good.copy();bad[1]={**bad[1],"finished":True}
 with pytest.raises(ValueError):adapter(bad)._delivery_extras()
 extra=good+[{"uid":0,"generation_index":n,"finished":n==200} for n in range(3,201)]
 with pytest.raises(ValueError):adapter(extra)._delivery_extras()
def test_terminal_cap_uses_real_base_adapter_and_keeps_postterminal_physical_extra(monkeypatch,tmp_path):
 root=Path(__file__).parents[1]/"e2base1"
 if not root.is_dir(): root=Path('/data2/FreeToken/wt/e2base1-ordinary-rewind')
 monkeypatch.setenv("FT_T10_CAPTURE_MAX_TOKENS","200")
 monkeypatch.syspath_prepend(str(root/"scripts"));monkeypatch.syspath_prepend(str(root/"python"))
 torch=pytest.importorskip("torch",reason="real base-adapter exercise needs the existing CPU torch dependency")
 from equiv_suite.service_capture import ServiceCaptureAdapter
 from freetoken.core import SamplingParams
 from freetoken.message import DetokenizeMsg,UserMsg
 class Sampler:
  def sample(self,logits,args):return logits.argmax(-1)
 class Engine:
  def __init__(self):self.sampler=Sampler()
  def forward_batch(self,batch,logits):
   for request in batch.reqs:request.device_len+=1
   return self.sampler.sample(logits,None)
 engine=Engine();expected=[{"uid":0,"generation_index":n,"logical_label":"t10"} for n in range(200)]
 adapter=w.install_terminal_cap(ServiceCaptureAdapter(tmp_path/"service",expected_queries=expected,max_captures=8,max_bytes=1_000_000,process_identity={"pid":1,"start_ticks":2,"execution_id":"cpu"}).attach(engine))
 adapter.admit_user_msg(UserMsg(uid=0,input_ids=torch.tensor([1,2],dtype=torch.int32),sampling_params=SamplingParams()))
 request=types.SimpleNamespace(uid=0,input_ids=torch.tensor([1,2],dtype=torch.int32),device_len=2)
 for logits in ([9.,1.],[1.,9.],[8.,1.],[1.,8.]):engine.forward_batch(types.SimpleNamespace(reqs=[request]),torch.tensor([logits]))
 for token,finished in ((0,False),(1,False),(0,True)):adapter.observe_detokenize(DetokenizeMsg(uid=0,next_token=token,finished=finished))
 assert adapter.finalize()["terminal"]=="complete"
 report=json.loads((tmp_path/"service"/"service_delivery.json").read_text())
 assert report["t10_terminal_cap"]["actual_delivery_counts"]=={"0":3} and report["un_delivered_samples"]==[{"uid":0,"generation_index":3,"sampled_token_id":1,"delivered":False,"reason":"physical sample after delivered terminal generation"}]
def test_execute_runs_two_groups_three_processes_and_only_raw_result(monkeypatch,tmp_path):
 _mock_review_and_root(monkeypatch,tmp_path,'rounds')
 calls=[]
 monkeypatch.setattr(m,"bind_inputs",lambda _:m.TRACES)
 class D:
  require_closed_round=lambda self,rid,verdict:None
  ATOMIC_HELPER_SHA="pin"
  def require_t20_failed_harness(self): p=tmp_path/"t20.json";p.write_text("{}");return p
  def load_owned_lifecycle(self):return types.SimpleNamespace(verified_module=lambda *_:types.SimpleNamespace(next_batch=lambda _:91),stop_owned_process=lambda _:calls.append("stop"))
  def take_d07_gpu_lock(self,r,b):calls.append("lock");return {"owner":r,"batch":b}
  def release_d07_gpu_lock(self,_):calls.append("unlock")
  def require_gpu_idle(self):return [0]
  def dynamic_fixture_port(self):return 43123
  def write_new(self,p,d):m.write_new(p,d)
 identity={"model_path":"m","server_port":"<dynamic-port>","prefill_layer_major":"False","max_prefill_length":"4096","max_extend_tokens":"4096","mamba_host_slots":"0","enable_cache_report":"True","special_token_ckpt":"True","_unique_suffix":"'.pid=1'"}
 d=D();d.LOCK=tmp_path/'gpu.lock';d.require_child_receipt=lambda *_a,**_k:{};monkeypatch.setattr(m,"load_d07",lambda:d);monkeypatch.setattr(m,"packet",lambda _ :{"old_33_36_evidence":{"sha256":"x"}});monkeypatch.setattr(m,"start_mode",lambda *_:calls.append("start") or object());monkeypatch.setattr(m,"serve_identity",lambda *_:{"normalized":dict(identity),"parsed":dict(identity),"serve_log_sha256":"x","owned_process":{}})
 monkeypatch.setattr(m,"capture_bindings",lambda _:{"sampler_root":"/unused","uids":{str(i):{"input_ids_sha256":"receipt","sampled_token_ids":[1,99]} for i in range(24)}})
 def replay(_wt,_port,phase,_trace,_out,_log,_d):return {f"k{i}":{"round":i,"text":f"{phase}-{i}","completion_tokens":2,"cached_tokens":i if phase=="warm" else 0,"uid":i+(12 if phase=="warm" else 0),"finish_reason":"stop","parts":["x"]} for i in range(12)}
 monkeypatch.setattr(m,"invoke_replay",replay);monkeypatch.setattr(m.sys,"platform","linux")
 result=m.execute(tmp_path/"wt",tmp_path/"rounds",owned_child=True,batch=91,launch_receipt=tmp_path/'receipt');run=tmp_path/"rounds"/m.RID
 assert result["verdict"]=="pending_review" and set(result["groups"])=={"ordinary","layer_major"}
 assert len(calls)==14 and calls.count("start")==6 and calls.count("stop")==6
 assert (run/"result.json").is_file() and not (run/"round.json").exists() and not (run/"MANIFEST.sha256").exists()
def test_execute_failure_stops_owned_service_and_releases_lock(monkeypatch,tmp_path):
 _mock_review_and_root(monkeypatch,tmp_path,'rounds')
 calls=[]
 monkeypatch.setattr(m,"bind_inputs",lambda _:m.TRACES)
 class D:
  require_closed_round=lambda self,rid,verdict:None
  ATOMIC_HELPER_SHA="pin"
  def require_t20_failed_harness(self):p=tmp_path/"t20";p.write_text("{}");return p
  def load_owned_lifecycle(self):return types.SimpleNamespace(verified_module=lambda *_:types.SimpleNamespace(next_batch=lambda _:1),stop_owned_process=lambda _:calls.append("stop"))
  def take_d07_gpu_lock(self,*_):return {"owner":"T","batch":1}
  def release_d07_gpu_lock(self,_):calls.append("unlock")
  def require_gpu_idle(self):return [0]
  def dynamic_fixture_port(self):return 43211
  def write_new(self,p,d):m.write_new(p,d)
 d=D();d.LOCK=tmp_path/'gpu.lock';d.require_child_receipt=lambda *_a,**_k:{};monkeypatch.setattr(m,"load_d07",lambda:d);monkeypatch.setattr(m,"packet",lambda _ :{"old_33_36_evidence":{}});monkeypatch.setattr(m,"start_mode",lambda *_:object())
 monkeypatch.setattr(m,"invoke_replay",lambda *_:(_ for _ in ()).throw(RuntimeError("client failed")));monkeypatch.setattr(m.sys,"platform","linux")
 with pytest.raises(RuntimeError):m.execute(tmp_path/"wt",tmp_path/"rounds",owned_child=True,batch=1,launch_receipt=tmp_path/'receipt')
 assert calls==["stop","unlock"] and (tmp_path/"rounds"/m.RID/"failed_harness.json").is_file()
def test_controller_reserves_and_default_main_never_allocates(monkeypatch,tmp_path,capsys):
 _mock_review_and_root(monkeypatch,tmp_path,'out')
 closure=tmp_path/'t20';closure.write_text('{}');calls=[]
 class Owned:
  def verified_module(self,*_):return types.SimpleNamespace(next_batch=lambda _:73)
  def reserve_process(self,h,b,r,a,p,v):calls.append((b,r,a,v));p.write_text(json.dumps({**v,'state':'launched','batch_pid':321}));return json.loads(p.read_text())
  def process_identity(self,pid):return {'pid':pid,'start_ticks':4}
  def publish_receipt(self,p,_i,v):p.write_text(json.dumps(v))
 class D:
  require_closed_round=lambda self,rid,verdict:None
  ATOMIC_HELPER_SHA='x';OWNED_PROTOCOL_SHA='y';LOCK=tmp_path/'gpu.lock'
  def require_t20_failed_harness(self):return closure
  def load_owned_lifecycle(self):return Owned()
  def process_birth(self):return {'pid':1,'start_ticks':2,'execution_id':'1:2'}
  def argv_sha256(self,a):return __import__('hashlib').sha256(json.dumps(a,separators=(',',':')).encode()).hexdigest()
  def publish_child_binding(self,*a,**k):return __import__('importlib').import_module('types').SimpleNamespace() if False else __import__('json').loads(a[1] and json.dumps({**a[1],'child':a[2]}))
 (tmp_path/'out').mkdir();d=D();monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{'p':1});monkeypatch.setattr(m.sys,'platform','linux')
 result=m.execute(tmp_path/'wt',tmp_path/'out');assert calls[0][0]==73 and result['child']['pid']==321 and (tmp_path/'out'/'launch_E2-R044_batch73.json').is_file()
 monkeypatch.setattr(m,'packet',lambda _:{'preflight':True});monkeypatch.setattr(m,'execute',lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('allocated')))
 m.main(['--worktree',str(tmp_path)]);assert json.loads(capsys.readouterr().out)=={'preflight':True}

def test_controller_reservation_conflict_stops_before_child_or_gpu_lock(monkeypatch,tmp_path):
 _mock_review_and_root(monkeypatch,tmp_path,'out')
 calls=[];closure=tmp_path/'t20';closure.write_text('{}')
 class Owned:
  def verified_module(self,*_):return types.SimpleNamespace(next_batch=lambda _:74)
  def reserve_process(self,*_):calls.append('reserve');raise FileExistsError('receipt exists')
 class D:
  require_closed_round=lambda self,rid,verdict:None
  ATOMIC_HELPER_SHA='x';OWNED_PROTOCOL_SHA='y';LOCK=tmp_path/'gpu.lock'
  def require_t20_failed_harness(self):return closure
  def load_owned_lifecycle(self):return Owned()
  def process_birth(self):return {'pid':1,'start_ticks':2,'execution_id':'1:2'}
  def argv_sha256(self,a):return 'argv'
  def take_d07_gpu_lock(self,*_):calls.append('gpu-lock');raise AssertionError('controller must not take GPU lock')
 monkeypatch.setattr(m,'load_d07',lambda:D());monkeypatch.setattr(m,'packet',lambda _:{'p':1});monkeypatch.setattr(m.sys,'platform','linux')
 with pytest.raises(FileExistsError):m.execute(tmp_path/'wt',tmp_path/'out')
 assert calls==['reserve']

def test_child_rejects_wrong_receipt_before_packet_or_gpu_lock(monkeypatch,tmp_path):
 calls=[]
 monkeypatch.setattr(m,"bind_inputs",lambda _:m.TRACES)
 class D:
  def require_child_receipt(self,*_a,**_k):raise RuntimeError('receipt binding mismatch')
  def take_d07_gpu_lock(self,*_):calls.append('gpu-lock')
 monkeypatch.setattr(m,'load_d07',lambda:D());monkeypatch.setattr(m,'packet',lambda _:(calls.append('packet') or {}));monkeypatch.setattr(m.sys,'platform','linux')
 with pytest.raises(RuntimeError,match='receipt binding mismatch'):
  m.execute(tmp_path/'wt',tmp_path/'out',owned_child=True,batch=74,launch_receipt=tmp_path/'receipt')
 assert calls==[]

@pytest.mark.parametrize('failure',['foreign_lock','unsealed_r052'])
def test_admission_rejects_before_packet_raw_or_batch(monkeypatch,tmp_path,failure):
 _mock_review_and_root(monkeypatch,tmp_path,'rounds')
 calls=[]
 class D:
  LOCK=tmp_path/'gpu.lock'
  def require_t20_failed_harness(self):calls.append('t20');return tmp_path/'t20'
  def require_closed_round(self,rid,verdict):
   calls.append((rid,verdict))
   if failure=='unsealed_r052':raise RuntimeError('R052 not sealed')
  def load_owned_lifecycle(self):pytest.fail('must reject before batch allocation')
 if failure=='foreign_lock':D.LOCK.write_text('foreign')
 monkeypatch.setattr(m,'load_d07',lambda:D());monkeypatch.setattr(m.sys,'platform','linux')
 monkeypatch.setattr(m,'packet',lambda _:pytest.fail('must reject before retained input preparation'))
 with pytest.raises(RuntimeError):m.execute(tmp_path/'wt',tmp_path/'rounds')
 if failure=='foreign_lock':assert calls==[]
 else:assert calls==['t20',('E2-R052','failed_harness')]

def test_business_inputs_bound_once_and_drift_rejected(monkeypatch,tmp_path):
 traces={};expected={}
 for name in ['cold','warm']:
  path=tmp_path/(name+'.json');path.write_text(json.dumps({'name':name}));traces[name]=path;expected[name]=m.sha(path)
 monkeypatch.setattr(m,'TRACES',traces);monkeypatch.setattr(m,'TRACE_SHA',expected)
 monkeypatch.setattr(m,'trace_rows',lambda _: {})
 run=tmp_path/'run';run.mkdir();bound=m.bind_inputs(run)
 try:
  assert all(p.read_bytes()==traces[k].read_bytes() and not p.stat().st_mode&0o222 for k,p in bound.items())
 finally:
  for p in bound.values():p.chmod(0o644)
 traces['cold'].write_text('{}');other=tmp_path/'other';other.mkdir()
 with pytest.raises(RuntimeError,match='business trace SHA'):m.bind_inputs(other)
 assert not list(other.iterdir())

def test_retained_metadata_registration_never_reads_raw_inputs(monkeypatch,tmp_path):
 old=tmp_path/'phase1_manifest.json';old.write_text('DO NOT READ')
 paths={'cold':tmp_path/'forward_trace.json','warm':tmp_path/'reverse_trace.json'}
 for p in paths.values():p.write_text('DO NOT READ')
 round_file=tmp_path/'round.json';round_file.write_text(json.dumps({'verdict':'kept','verdict_history':[{'new':'kept'}]}))
 manifest=tmp_path/'MANIFEST.sha256';manifest.write_text('a'*64+'  ./phase1_manifest.json\n'+'b'*64+'  ./forward_trace.json\n'+'c'*64+'  ./reverse_trace.json\n')
 monkeypatch.setattr(m,'OLD',old);monkeypatch.setattr(m,'TRACES',paths);monkeypatch.setattr(m,'TRACE_SHA',{'cold':'b'*64,'warm':'c'*64})
 monkeypatch.setattr(m,'OLD_SHA','a'*64);monkeypatch.setattr(m,'R017_ROUND_SHA',m.sha(round_file));monkeypatch.setattr(m,'R017_MANIFEST_SHA',m.sha(manifest))
 for p in [round_file,manifest]:p.chmod(0o444)
 original=Path.read_bytes
 def guarded(self):
  if self in [old,*paths.values()]:pytest.fail('raw predecessor read before lock')
  return original(self)
 monkeypatch.setattr(Path,'read_bytes',guarded)
 try:assert m.retained_registration()['cold']['sha256']=='b'*64
 finally:
  for p in [round_file,manifest]:p.chmod(0o644)

def test_startup_cleanup_failure_keeps_lock_even_if_group_is_gone(monkeypatch,tmp_path):
 _mock_review_and_root(monkeypatch,tmp_path,'rounds')
 calls=[];closure=tmp_path/'t20';closure.write_text('{}')
 proc=types.SimpleNamespace(pid=88)
 class D:
  LOCK=tmp_path/'gpu.lock'
  def require_t20_failed_harness(self):return closure
  def require_closed_round(self,*_):return closure
  def require_child_receipt(self,*_,**__):return {}
  def take_d07_gpu_lock(self,*_):calls.append('lock');return {'owner':m.RID}
  def release_d07_gpu_lock(self,*_):calls.append('unlock')
  def require_gpu_idle(self):return [0]
  def dynamic_fixture_port(self):return 41000
  def load_owned_lifecycle(self):return types.SimpleNamespace(owned_group_alive=lambda _:False,stop_owned_process=lambda _:calls.append('retry'))
 def fail(*_):
  error=RuntimeError('startup stop failure');error.owned_process=proc;error.owned_cleanup_failed=True;raise error
 monkeypatch.setattr(m,'load_d07',lambda:D());monkeypatch.setattr(m.sys,'platform','linux')
 monkeypatch.setattr(m,'packet',lambda _:{'old_33_36_evidence':{}});monkeypatch.setattr(m,'bind_inputs',lambda _:m.TRACES)
 monkeypatch.setattr(m,'start_mode',fail)
 with pytest.raises(RuntimeError,match='preserve GPU lock'):
  m.execute(tmp_path/'wt',tmp_path/'rounds',owned_child=True,batch=9,launch_receipt=tmp_path/'receipt')
 assert calls==['lock']


def _mock_review_and_root(monkeypatch,tmp_path,name):
 monkeypatch.setattr(m,'ROUNDS',tmp_path/name)
 review=tmp_path/'sealed_review.json';review.write_text('{}')
 monkeypatch.setattr(m,'require_startup_review',lambda:review)

@pytest.mark.parametrize('drift',[None,'writable','tampered','output','source','missing'])
def test_sealed_review_sha_and_actual_source_output_binding(monkeypatch,tmp_path,drift):
 directory=tmp_path/'review';directory.mkdir();review=directory/'review.json';pin=directory/'pin.json'
 monkeypatch.setattr(m,'REVIEW_DIR',directory);monkeypatch.setattr(m,'startup_source_hashes',lambda:{'actual.py':'a'*64})
 monkeypatch.setattr(m,'require_file_dry_receipt',lambda _: {'path':'filedry','sha256':'dry_sha'})
 value={'schema':'ft_t10_startup_review/v3','rid':m.RID,'candidate_commit':m.CANDIDATE,'approved':True,'verdict':'PASS','output_root':str(m.ROUNDS),'source_sha256':m.startup_source_hashes(),'file_dry_receipt':'filedry','file_dry_receipt_sha256':'dry_sha'}
 if drift=='output':value['output_root']='/tmp/forged'
 if drift=='source':value['source_sha256']={'actual.py':'b'*64}
 review.write_text(json.dumps(value));pin.write_text(json.dumps({'schema':'ft_t10_startup_review_pin/v1','rid':m.RID,'review_path':str(review),'review_sha256':m.sha(review)}))
 if drift=='tampered':review.write_text('{}')
 if drift=='missing':pin.unlink()
 for path in [review,pin]:
  if path.exists():path.chmod(0o444)
 if drift!='writable':directory.chmod(0o555)
 try:
  if drift is None:assert m.require_startup_review()==review
  else:
   with pytest.raises(RuntimeError,match='startup review'):m.require_startup_review()
 finally:
  directory.chmod(0o755)
  for path in [review,pin]:
   if path.exists():path.chmod(0o644)

def test_arbitrary_output_root_rejected_before_queue_and_batch(monkeypatch,tmp_path):
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'load_d07',lambda:object())
 monkeypatch.setattr(m,'require_queue',lambda _:pytest.fail('wrong output admitted to queue'))
 with pytest.raises(RuntimeError,match='canonical'):
  m.execute(tmp_path/'wt',tmp_path/'wrong')
 with pytest.raises(RuntimeError,match='canonical'):
  m.require_output_root(m.ROUNDS/'..'/'ft_rounds')

def test_runtime_capture_path_exists_and_copies_are_writable(tmp_path):
 copied=m.copy_runtime_sources(tmp_path/'source')
 assert (tmp_path/'source'/m.CAPTURE_STARTUP.name).is_file()
 assert len(copied)==7
 for row in copied:
  path=Path(row['copy'])
  assert m.sha(path)==m.sha(row['source']) and path.stat().st_mode&0o200

def test_file_dry_rejects_formal_round_and_noncanonical_path(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'ROUNDS',tmp_path/'formal')
 monkeypatch.setattr(m,'packet',lambda _:pytest.fail('path must be checked before packet'))
 for output in (m.ROUNDS/m.RID,tmp_path/'.dryrun_R044_wrong',m.ROUNDS/'.dryrun_R044_nested'/'x'):
  with pytest.raises(RuntimeError,match='canonical hidden sibling'):m.file_dry_run(output)


def test_file_dry_refuses_missing_queue_before_creating_output(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'ROUNDS',tmp_path)
 monkeypatch.setattr(m,'load_d07',lambda:object())
 monkeypatch.setattr(m,'require_queue',lambda _:(_ for _ in ()).throw(RuntimeError('missing predecessor')))
 monkeypatch.setattr(m,'packet',lambda _:pytest.fail('must not read retained inputs before queue'))
 target=tmp_path/'.dryrun_R044_missing'
 with pytest.raises(RuntimeError,match='missing predecessor'):m.file_dry_run(target)
 assert not target.exists()
