import importlib.util, json, os
from pathlib import Path
import pytest
p=Path(__file__).parents[1]/'r048_t09_prepare_v6.py';s=importlib.util.spec_from_file_location('r048',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def good(cmd):
 if 'rev-parse' in cmd:return m.CANDIDATE
 if 'status' in cmd:return ''
 return 'ancestor'
def test_admission_metadata_and_s_repeat(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'git',good);monkeypatch.setattr(m.subprocess,'run',lambda *_a,**_k:type('R',(),{'returncode':0})())
 seen=[]
 def closure(rid,verdict):seen.append((rid,verdict));return tmp_path/rid
 r=m.admission(closure,tmp_path,tmp_path/'lock')
 assert r['arms']==['V0','A','B','C','S'] and 'repeat' in r['S']
 assert seen==[('E2-R040','failed_harness'),('E2-R050-gate-D15','kept'),('E2-R051-gate-D08','kept'),('E2-R049a','measured'),('E2-R049','failed_harness')]
@pytest.mark.parametrize('kind',["lock","head","dirty","ancestor"])
def test_failures_precede_any_lifecycle(monkeypatch,tmp_path,kind):
 lock=tmp_path/'lock'
 if kind=='lock':lock.write_text('x')
 def fake(cmd):
  if 'rev-parse' in cmd:return 'bad' if kind=='head' else m.CANDIDATE
  if 'status' in cmd:return 'x' if kind=='dirty' else ''
  return 'no' if kind=='ancestor' else 'ancestor'
 monkeypatch.setattr(m,'git',fake)
 monkeypatch.setattr(m.subprocess,'run',lambda *_a,**_k:type('R',(),{'returncode':1 if kind=='ancestor' else 0})())
 with pytest.raises(RuntimeError):m.admission(lambda rid,v:tmp_path/rid,tmp_path,lock)

def test_controller_rejects_unready_body_before_any_admission_or_batch(monkeypatch):
 monkeypatch.setattr(m,'load_d07',lambda:pytest.fail('must not load lifecycle'))
 monkeypatch.setattr(m,'admission',lambda *_:pytest.fail('must not admit'))
 with pytest.raises(RuntimeError,match='body is not ready'):m.controller(body_ready=False)

def test_controller_reserves_once_and_publishes_matching_birth(monkeypatch,tmp_path):
 calls=[]
 class Helper:
  def next_batch(self,root):
   calls.append(('next_batch',root));return 83
 class Owned:
  def verified_module(self,path,digest,name):
   calls.append(('verified',path,digest,name));return Helper()
  def reserve_process(self,helper,batch,rid,argv,receipt,value):
   calls.append(('reserve',batch,rid,argv,receipt,value));return {'batch_pid':2468,'batch':batch,'rid':rid}
  def process_identity(self,pid):
   calls.append(('identity',pid));return {'pid':pid,'start_ticks':97531}
 owned=Owned()
 class D:
  ATOMIC_HELPER_SHA='atomic-sha'
  @staticmethod
  def require_closed_round(rid,verdict): return {'rid':rid,'verdict':verdict}
  @staticmethod
  def load_owned_lifecycle(): calls.append(('lifecycle',));return owned
  @staticmethod
  def argv_sha256(argv): return 'argv-sha'
  @staticmethod
  def process_birth(): return {'pid':123,'start_ticks':456}
  @staticmethod
  def publish_child_binding(receipt,got,birth,*,lifecycle):
   calls.append(('publish',receipt,got,birth,lifecycle));return {'receipt':str(receipt),'birth':birth}
 admitted=[]
 def admit(require_round):
  admitted.append(require_round);calls.append(('admission',));return {'ok':True}
 monkeypatch.setattr(m,'ROOT',tmp_path)
 monkeypatch.setattr(m,'VENV',tmp_path/'venv')
 monkeypatch.setattr(m,'BATCH_ROOT',tmp_path/'shared/ft_rounds')
 def full_body(_batch): return {'not_called':True}
 full_body.full_implementation=True
 monkeypatch.setattr(m,'run_measurements',full_body)
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m,'admission',admit)
 monkeypatch.setattr(m,'require_launch_review',lambda:calls.append(('review',)) or {})
 result=m.controller(body_ready=True)
 assert admitted==[D.require_closed_round]
 reserve=next(item for item in calls if item[0]=='reserve')
 assert reserve[1:3]==(83,m.RID)
 assert reserve[3]==[str(tmp_path/'venv/bin/python'),str(Path(m.__file__).resolve()),'--run','--owned-child','--batch','83','--launch-receipt',str(tmp_path/'runs/dev_R048/launch_E2-R048_batch83.json')]
 assert reserve[5]['state']=='reserved' and reserve[5]['argv_sha256']=='argv-sha'
 assert result['birth']=={'pid':2468,'start_ticks':97531,'execution_id':'2468:97531'}
 assert ('next_batch',tmp_path/'shared/ft_rounds') in calls
 assert [item[0] for item in calls]==['admission','review','lifecycle','verified','next_batch','reserve','identity','publish']

def test_child_wrong_receipt_rejects_before_gpu_lock(monkeypatch):
 class D:
  @staticmethod
  def require_closed_round(*_): return {}
  @staticmethod
  def require_child_receipt(*_a,**_k): raise RuntimeError('binding differs')
  @staticmethod
  def take_d07_gpu_lock(*_): pytest.fail('receipt failure must precede lock')
 def full_body(_batch): return {}
 full_body.full_implementation=True
 monkeypatch.setattr(m,'run_measurements',full_body)
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m,'admission',lambda _: {})
 monkeypatch.setattr(m,'require_launch_review',lambda:{})
 with pytest.raises(RuntimeError,match='binding differs'):m.child(9,Path('/tmp/receipt.json'),body_ready=True)

def test_child_unready_body_rejects_before_loading_or_locking(monkeypatch):
 monkeypatch.setattr(m,'load_d07',lambda:pytest.fail('unready child must not load D07'))
 with pytest.raises(RuntimeError,match='business body is not ready'):m.child(9,Path('/tmp/receipt.json'),body_ready=False)

def test_child_cleanup_failure_preserves_lock(monkeypatch):
 released=[];calls=[]
 class D:
  @staticmethod
  def require_closed_round(*_): return {}
  @staticmethod
  def require_child_receipt(*_a,**_k): calls.append('receipt');return {}
  @staticmethod
  def take_d07_gpu_lock(*_): calls.append('lock');return {'owner':'R048'}
  @staticmethod
  def release_d07_gpu_lock(owner): released.append(owner)
 def full_body(_batch):
  error=RuntimeError('group remains');error.owned_cleanup_failed=True;raise error
 full_body.full_implementation=True
 monkeypatch.setattr(m,'run_measurements',full_body)
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m,'admission',lambda _: calls.append('admission'))
 monkeypatch.setattr(m,'require_launch_review',lambda:calls.append('review') or {})
 with pytest.raises(RuntimeError,match='group remains'):m.child(9,Path('/tmp/receipt.json'),body_ready=True)
 assert calls==['admission','review','receipt','lock'] and released==[]

def test_child_success_releases_its_lock(monkeypatch):
 released=[];calls=[]
 class D:
  @staticmethod
  def require_closed_round(*_): return {}
  @staticmethod
  def require_child_receipt(*_a,**_k): calls.append('receipt');return {}
  @staticmethod
  def take_d07_gpu_lock(*_): calls.append('lock');return {'owner':'R048'}
  @staticmethod
  def release_d07_gpu_lock(owner): released.append(owner)
 def full_body(batch): calls.append(('measure',batch));return {'ok':True}
 full_body.full_implementation=True
 monkeypatch.setattr(m,'run_measurements',full_body)
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m,'admission',lambda _: calls.append('admission'))
 monkeypatch.setattr(m,'require_launch_review',lambda:calls.append('review') or {})
 assert m.child(9,Path('/tmp/receipt.json'),body_ready=True)=={'ok':True}
 assert calls==['admission','review','receipt','lock',('measure',9)] and released==[{'owner':'R048'}]

def test_child_ordinary_measurement_failure_releases_lock(monkeypatch):
 released=[]
 class D:
  @staticmethod
  def require_closed_round(*_): return {}
  @staticmethod
  def require_child_receipt(*_a,**_k): return {}
  @staticmethod
  def take_d07_gpu_lock(*_): return {'owner':'R048'}
  @staticmethod
  def release_d07_gpu_lock(owner): released.append(owner)
 def full_body(_batch): raise RuntimeError('measurement failed')
 full_body.full_implementation=True
 monkeypatch.setattr(m,'run_measurements',full_body)
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m,'admission',lambda _: {})
 monkeypatch.setattr(m,'require_launch_review',lambda:{})
 with pytest.raises(RuntimeError,match='measurement failed'):m.child(9,Path('/tmp/receipt.json'),body_ready=True)
 assert released==[{'owner':'R048'}]

def test_t09_service_argv_has_exact_arm_prefix_hybrid_and_no_lm():
 class D:
  @staticmethod
  def serve_argv(port): return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--memory-ratio','0.88','--moe-strategy','offload','--max-prefill-length','4096','--prefill-layer-major']
 argv=m.service_argv(D,17777,'S')
 assert argv[argv.index('--kv-reserve-tokens')+1]=='98304' and argv[argv.index('--max-seq-len-override')+1]=='98304'
 assert argv[argv.index('--memory-ratio')+1]=='0.88'
 assert argv[:len(m.ARM_PREFIXES['A'])]==m.ARM_PREFIXES['A']
 assert argv[argv.index('--moe-strategy')+1]=='hybrid'
 assert '--prefill-layer-major' not in argv and argv[argv.index('--max-prefill-length')+1]=='4096'

def test_start_service_uses_private_group_and_diagnostic_trace(monkeypatch,tmp_path):
 writes=[];captured={}
 class Owned:
  @staticmethod
  def process_identity(pid): return {'pid':pid,'pgid':pid,'session':pid,'start_ticks':1}
 class D:
  @staticmethod
  def clean_environment(_): return {'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'python','VIRTUAL_ENV':'venv'}
  @staticmethod
  def serve_argv(port): return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--memory-ratio','0.88','--moe-strategy','offload','--max-prefill-length','4096','--prefill-layer-major']
  @staticmethod
  def write_new(path,value): writes.append((path,value))
  @staticmethod
  def load_owned_lifecycle(): return Owned()
 class P:
  pid=77;returncode=None
  @staticmethod
  def poll(): return None
 def popen(argv,**kwargs):
  captured.update(argv=argv,**kwargs);kwargs['stdout'].write('Parsed arguments\nactual=true\n');kwargs['stdout'].flush();return P()
 class Response:
  def __enter__(self): return self
  def __exit__(self,*_): return False
  def read(self,*_): return b'{"status":"ok"}'
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m.subprocess,'Popen',popen)
 monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_a,**_k:Response())
 monkeypatch.setattr(m.time,'monotonic',lambda:0)
 arm=tmp_path/'A';arm.mkdir()
 assert m.start_service(arm,'A',tmp_path,17777,phase='diagnostic').pid==77
 assert captured['start_new_session'] is True and captured['argv'][:len(m.ARM_PREFIXES['A'])]==m.ARM_PREFIXES['A']
 assert captured['env']['FT_DEV_D0']=='1' and captured['env']['FT_DEV_HYB_TRACE']=='1'
 assert any(path.name=='owned_process.json' for path,_ in writes) and any(path.name=='health.json' for path,_ in writes)
 assert (arm/'serve_args.txt').read_text(encoding='utf-8')=='Parsed arguments\nactual=true\n'

def test_service_files_persist_only_allowed_environment(monkeypatch,tmp_path):
 class D:
  @staticmethod
  def clean_environment(_): return {'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'python','VIRTUAL_ENV':'venv','FT_SSH_PASSWORD':'leak','OTHER_SECRET':'leak'}
  @staticmethod
  def serve_argv(port): return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--memory-ratio','0.88','--moe-strategy','offload','--max-prefill-length','4096']
  @staticmethod
  def write_new(path,value): path.write_text(json.dumps(value),encoding='utf-8')
 arm=tmp_path/'A';arm.mkdir();m.write_service_files(D,arm,'A',tmp_path,17777,dry_run=True)
 persisted=(arm/'ENV.txt').read_text(encoding='utf-8')+(arm/'SERVE_CMD.txt').read_text(encoding='utf-8')
 assert 'leak' not in persisted and 'FT_SSH_PASSWORD' not in persisted and 'OTHER_SECRET' not in persisted

def test_actual_args_missing_from_log_fails_closed(tmp_path):
 arm=tmp_path/'A';arm.mkdir();(arm/'serve.log').write_text('no parser banner\n',encoding='utf-8')
 with pytest.raises(RuntimeError,match='Parsed arguments'): m.write_actual_serve_args(arm)

def test_start_readiness_cleanup_failure_attaches_owned_process(monkeypatch,tmp_path):
 class Owned:
  @staticmethod
  def process_identity(pid): return {'pid':pid,'pgid':pid,'session':pid,'start_ticks':1}
  @staticmethod
  def stop_owned_process(_): raise RuntimeError('stop failed')
 class D:
  @staticmethod
  def clean_environment(_): return {'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'python','VIRTUAL_ENV':'venv'}
  @staticmethod
  def serve_argv(port): return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--memory-ratio','0.88','--moe-strategy','offload','--max-prefill-length','4096']
  @staticmethod
  def write_new(*_): pass
  @staticmethod
  def load_owned_lifecycle(): return Owned()
 class P:
  pid=78;returncode=17
  @staticmethod
  def poll(): return 17
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m.subprocess,'Popen',lambda *_a,**_k:P())
 arm=tmp_path/'B';arm.mkdir()
 with pytest.raises(RuntimeError,match='stop failed') as error:m.start_service(arm,'B',tmp_path,17778)
 assert getattr(error.value,'owned_process').pid==78 and error.value.owned_cleanup_failed is True

def test_run_workloads_file_dry_uses_ordinary_artifact_shape(monkeypatch,tmp_path):
 class D:
  COLD_RAW_SHA='cold-sha';PROBE_RAW_SHA='probe-sha';MODEL='model'
  @staticmethod
  def verify_frozen_cold_helpers(): return {'cold_eq_raw':'/frozen/cold.py','probe_raw':'/frozen/probe.py','cold_eq_raw_sha256':'cold-sha','probe_raw_sha256':'probe-sha'}
  @staticmethod
  def write_new(path,value): path.write_text(json.dumps(value),encoding='utf-8')
  @staticmethod
  def clean_environment(_): return {'CUDA_VISIBLE_DEVICES':'0'}
 monkeypatch.setattr(m,'load_d07',lambda:D)
 result=m.run_workloads(tmp_path,17779,file_dry_run=True)
 assert result['transport']=='ordinary_sse_no_ft_dev_ack' and result['phase']=='performance'
 assert (tmp_path/'first_shot.payload.json').is_file() and (tmp_path/'two_decode.json').is_file()

def test_parameterized_frozen_cold_helper_receives_actual_t09_argv(tmp_path):
 probe=tmp_path/'probe_ft_cold32k.py';probe.write_text("URL=''\n",encoding='utf-8')
 cold=tmp_path/'cold_eq.py';cold.write_text("import json, sys\nfrom probe_ft_cold32k import URL\njson.dump({'argv':sys.argv,'url':URL},open(sys.argv[2],'w'))\n",encoding='utf-8')
 class D:
  COLD_RAW_SHA='cold-sha';PROBE_RAW_SHA='probe-sha'
  @staticmethod
  def verify_frozen_cold_helpers(): return {'cold_eq_raw':str(cold),'probe_raw':str(probe),'cold_eq_raw_sha256':'cold-sha','probe_raw_sha256':'probe-sha'}
 output=tmp_path/'out.json'
 m.invoke_frozen_cold_eq(D,17780,'same-id',output,2000,64)
 raw=json.loads(output.read_text())
 assert raw['argv']==[str(cold),'same-id',str(output),'2000','64'] and raw['url']=='http://127.0.0.1:17780/v1/chat/completions'

def test_prepare_exercises_each_arm_output_and_port_without_service_or_lock(monkeypatch,tmp_path):
 calls=[]
 class D:
  @staticmethod
  def require_closed_round(rid,verdict): return {"rid":rid,"verdict":verdict}
  @staticmethod
  def dynamic_fixture_port(): return 20000+len(calls)
  @staticmethod
  def clean_environment(_): return {'CUDA_VISIBLE_DEVICES':'','PYTHONPATH':'python','VIRTUAL_ENV':'venv'}
  @staticmethod
  def serve_argv(port): return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--memory-ratio','0.88','--moe-strategy','offload','--max-prefill-length','4096','--prefill-layer-major']
  @staticmethod
  def write_new(path,value): calls.append(path);path.write_text(json.dumps(value),encoding='utf-8')
  @staticmethod
  def verify_frozen_cold_helpers(): return {'cold_eq_raw_sha256':'cold','probe_raw_sha256':'probe'}
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m.subprocess,'Popen',lambda *_a,**_k:pytest.fail('file dry-run started a service'))
 monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_a,**_k:pytest.fail('file dry-run connected a socket'))
 monkeypatch.setattr(m,'admission',lambda require_round:{'closure':require_round('gate','kept')})
 monkeypatch.setattr(m,'source_binding',lambda:{'candidate_commit':m.CANDIDATE,'operator':{'uid':1,'user':'fixture'}})
 monkeypatch.setattr(m,'allocate_port_pair',lambda:(17777,{'api':17777,'tcpstore':17778,'probe':'fixture'}))
 result=m.prepare(tmp_path/'dry')
 assert result['service_started'] is False and result['gpu_lock_taken'] is False
 assert result['port_pair']['tcpstore']==result['port_pair']['api']+1
 assert all(value['port_pair']['api']==17777 for value in result['results']['arms'].values())
 assert result['receipt']['mode']=='0o444' and len(calls)>=100 and all(path.exists() for path in calls)
 for arm in ('V0','A','B','C','S'):
  for phase in ('performance','diagnostic'):
   for name in ('serve_argv.json','ENV.txt','SERVE_CMD.txt','serve_args.txt','serve.log','owned_process.json','health.json','d0_decode.json','d0_hyb_trace.jsonl','observer.json','first_shot.payload.json','two_decode.json'):
    assert (tmp_path/'dry'/arm/phase/name).is_file()

def test_prepare_rejects_formal_round_or_child_before_any_work(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'ROUND',tmp_path/'formal')
 monkeypatch.setattr(m,'ROUNDS',tmp_path)
 with pytest.raises(RuntimeError,match='formal round'):
  m.prepare(m.ROUND)
 with pytest.raises(RuntimeError,match='formal round'):
  m.prepare(m.ROUND/'child')

def test_main_dispatches_only_run_paths(monkeypatch,capsys):
 monkeypatch.setattr(m,'BODY_READY',True)
 monkeypatch.setattr(m,'controller',lambda **kwargs:{'route':'controller','kwargs':kwargs})
 monkeypatch.setattr(m,'child',lambda batch,receipt,**kwargs:{'route':'child','batch':batch,'receipt':str(receipt),'kwargs':kwargs})
 assert m.main(['--run'])==0 and json.loads(capsys.readouterr().out)['route']=='controller'
 assert m.main(['--run','--owned-child','--batch','12','--launch-receipt','receipt.json'])==0
 assert json.loads(capsys.readouterr().out)['route']=='child'

def test_main_prepare_dispatches_only_dry_run(monkeypatch,capsys,tmp_path):
 monkeypatch.setattr(m,'prepare',lambda directory:{'directory':str(directory)})
 assert m.main(['--prepare','--dry-run-dir',str(tmp_path/'dry')])==0
 assert json.loads(capsys.readouterr().out)=={'directory':str(tmp_path/'dry')}

def test_controller_rejects_missing_review_before_lifecycle(monkeypatch):
 class D:
  require_closed_round=staticmethod(lambda *_:{})
  load_owned_lifecycle=staticmethod(lambda:pytest.fail('review must precede lifecycle'))
 monkeypatch.setattr(m,'load_d07',lambda:D)
 monkeypatch.setattr(m,'admission',lambda *_:{})
 monkeypatch.setattr(m,'require_launch_review',lambda:(_ for _ in ()).throw(RuntimeError('review drift')))
 with pytest.raises(RuntimeError,match='review drift'):m.controller(body_ready=True)

def test_file_dry_receipt_rejects_source_drift(monkeypatch,tmp_path):
 receipt=tmp_path/'dry_run_receipt.json'
 sources={'r048_t09_prepare_v6.py':'one','d07_g3g4_prepare.py':'two'}
 binding={'operator':{'uid':1,'user':'fixture'}}
 doc={'schema':'ft_r048_real_path_dry_run/v4','rid':m.RID,'candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'source_sha256':sources,'owner_path':str(Path(m.__file__).resolve()),'uid':1,'user':'fixture','cwd':os.getcwd(),'formal_directory':str(m.ROUND),'formal_rid_directory_created':False,'passed':True,'binding':binding,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False}
 receipt.write_text(json.dumps(doc),encoding='utf-8');os.chmod(receipt,0o444)
 monkeypatch.setattr(m,'source_hashes',lambda:sources)
 monkeypatch.setattr(m,'source_binding',lambda:{'operator':{'uid':1,'user':'fixture'}})
 assert m.require_file_dry_run(receipt)==receipt
 monkeypatch.setattr(m,'source_hashes',lambda:{**sources,'r048_t09_prepare_v6.py':'drift'})
 with pytest.raises(RuntimeError,match='binding differs'):m.require_file_dry_run(receipt)

def test_candidate_trace_contract_is_default_off_and_has_completed_native_pcie_fields():
 root=Path(m.WT)/'python'/'freetoken'
 if not root.is_dir(): root=Path(__file__).parents[2]/'e2d08'/'python'/'freetoken'
 native=(root/'kernel/csrc/cpu_moe/cpu_moe_ext.cpp').read_text(encoding='utf-8')
 executor=(root/'moe/cpu_executor.py').read_text(encoding='utf-8')
 layer=(root/'layers/moe.py').read_text(encoding='utf-8')
 assert 'std::atomic<bool> trace_enabled{false}' in native
 assert 'out["start_ns"]' in native and 'out["end_ns"]' in native and 'out["barrier_wait_ns_total"]' in native
 assert '_HYB_TRACE_ENABLED = os.getenv("FT_DEV_HYB_TRACE", "0") == "1"' in executor
 assert '_HYB_TRACE = os.getenv("FT_DEV_HYB_TRACE", "0") == "1"' in layer
 assert 'if _HYB_TRACE:' in layer and 'torch.cuda.current_stream().synchronize()' in layer
 assert '"event_elapsed_ms"' in layer and '"completion_observed_host_ns"' in layer

def test_service_phase_separates_performance_from_diagnostic_and_removes_pause(tmp_path):
 class D:
  @staticmethod
  def clean_environment(_): return {'CUDA_VISIBLE_DEVICES':'','FT_DEV_PAUSE_ENDPOINT':'1','FT_DEV_D0':'1','FT_DEV_D0_PATH':'old','FT_DEV_HYB_TRACE':'1','PYTHONPATH':'python','VIRTUAL_ENV':'venv'}
  @staticmethod
  def serve_argv(port): return ['ft','serve','--port',str(port),'--kv-reserve-tokens','49152','--max-seq-len-override','49152','--memory-ratio','0.88','--moe-strategy','offload','--max-prefill-length','4096']
  @staticmethod
  def write_new(path,value): path.write_text(json.dumps(value),encoding='utf-8')
 perf=tmp_path/'performance';diag=tmp_path/'diagnostic';perf.mkdir();diag.mkdir()
 env,_=m.write_service_plan(D,perf,'V0',tmp_path,17777,phase='performance')
 assert not {'FT_DEV_PAUSE_ENDPOINT','FT_DEV_D0','FT_DEV_D0_PATH','FT_DEV_HYB_TRACE'}&set(env)
 env,_=m.write_service_plan(D,diag,'V0',tmp_path,17777,phase='diagnostic')
 assert env['FT_DEV_D0']=='1' and env['FT_DEV_HYB_TRACE']=='1' and env['FT_DEV_D0_PATH']==str(diag/'d0')

def test_actual_server_args_and_env_diff_only_allows_identity_suffix(tmp_path):
 def arm(name,suffix,extra='x'):
  p=tmp_path/name;p.mkdir()
  p.joinpath('serve.log').write_text(f"Parsed arguments: ServerArgs(server_port=17777, _unique_suffix='{suffix}', stable='{extra}')\n",encoding='utf-8')
  p.joinpath('ENV.txt').write_text(json.dumps({'environment':{'CUDA_VISIBLE_DEVICES':'','PYTHONPATH':'python'}}),encoding='utf-8')
  return p
 left,right=arm('V0','pid=1'),arm('A','pid=2')
 value=m.actual_args_env_diff(left,right,tmp_path/'ok.json')
 assert value['parsed_changed']==['_unique_suffix'] and value['environment_changed']==[]
 broken=arm('B','pid=3','different')
 with pytest.raises(RuntimeError,match='actual serve args/env differ'):
  m.actual_args_env_diff(left,broken,tmp_path/'bad.json')

def test_runtime_copy_is_private_writable_and_hash_bound(tmp_path):
 root,binding=m.copy_runtime_sources(tmp_path)
 assert root.is_dir() and binding['r046c_t06_ordinary_startup_v4.py']['sha256']==m.source_hashes()['r046c_t06_ordinary_startup_v4.py']
 if os.name!='nt':
  for item in binding.values():
   path=Path(item['path']);assert path.stat().st_mode&0o777==0o600
