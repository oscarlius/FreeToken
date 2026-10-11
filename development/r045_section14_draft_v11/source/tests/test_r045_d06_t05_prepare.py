import importlib.util, json, os
from pathlib import Path
import pytest
from types import SimpleNamespace

SPEC=importlib.util.spec_from_file_location('t05',Path(__file__).parents[1]/'r045_d06_t05_prepare.py');t05=importlib.util.module_from_spec(SPEC);assert SPEC.loader;SPEC.loader.exec_module(t05)
REAL_VERIFY_PAUSE_HELPERS=t05.verify_pause_helpers
REAL_DRY_RECEIPT=t05.require_dry_run_receipt
REAL_STARTUP_REVIEW=t05.require_startup_review
REAL_D16_METADATA=t05.d16_failed_metadata
REAL_ORDINARY_CAPABILITY=t05.require_t05_ordinary_capability
@pytest.fixture(autouse=True)
def _receipt_gate(monkeypatch):
 monkeypatch.setattr(t05,'require_dry_run_receipt',lambda:{'path':'dry-receipt','sha256':'d'*64})
 monkeypatch.setattr(t05,'require_startup_review',lambda receipt:{'path':'startup-review','sha256':'r'*64})
 monkeypatch.setattr(t05,'r055_failed_metadata',lambda:{'r055_gate_ended':True,'r055c_authorized':False,'default_path':{'partial_cold_verdict':'PASS'}})
 monkeypatch.setattr(t05,'d16_failed_metadata',lambda:{'metadata_only':True,'rounds':{'E2-R040a':{},'E2-R040c':{}}})
 monkeypatch.setattr(t05,'verify_pause_helpers',lambda:{'test_double':True})
 monkeypatch.setattr(t05,'require_t05_ordinary_capability',lambda:None)
 class OfflineSocket:
  def __enter__(self):return self
  def __exit__(self,*_):return False
  def bind(self,address):assert address==('127.0.0.1',0)
  def getsockname(self):return ('127.0.0.1',51449)
  def connect(self,*_):pytest.fail('CPU socket guard rejects connect')
 monkeypatch.setattr(t05.socket,'socket',lambda *a,**k:OfflineSocket())
 monkeypatch.setattr(t05.urllib.request,'urlopen',lambda *a,**k:pytest.fail('offline CPU tests must not send HTTP'))
def test_cpu_command_shape_keeps_card_contract():
 plan=t05.suite_plan(Path('/tmp/t05'))
 c=t05.commands(Path('/tmp/t05'),34567)
 assert len(c)==6 and all(row[0]=='ordinary-sse' and '8095' not in row for row in c)
 assert [(item['name'],item['reps']) for item in plan[:2]]==[('a_two_decode_diff',3),('a_two_decode_same',1)]
 assert plan[0]['same_prompt'] is False and plan[1]['same_prompt'] is True
 assert plan[-1]['kind']=='d06_diagnostic_only' and plan[-1]['H']==(1,8,32)
 assert 'D0 UID steps' in plan[-1]['reason']
def test_two_arm_window_and_dynamic_loopback_only():
 argv=t05.serve_argv(45678)
 assert argv[argv.index('--kv-reserve-tokens')+1]=='98304'
 assert argv[argv.index('--max-seq-len-override')+1]=='98304'
 assert argv[argv.index('--host')+1]=='127.0.0.1' and argv[argv.index('--port')+1]=='45678'
def test_strict_arg_reader_allows_only_pid(tmp_path):
 a=tmp_path/'a.log';b=tmp_path/'b.log'
 a.write_text("Parsed arguments ServerArgs(model_path='/model', server_port=45678, special_token_ckpt=True, _unique_suffix='.pid=1', kv_reserve_tokens=73728)\n")
 b.write_text("Parsed arguments ServerArgs(model_path='/model', server_port=45678, special_token_ckpt=True, _unique_suffix='.pid=2', kv_reserve_tokens=73728)\n")
 t05.strict_log_args(a,b)
 b.write_text(b.read_text().replace('server_port=45678','server_port=45679'))
 with pytest.raises(ValueError,match='configuration changed'):
  t05.strict_log_args(a,b)

def test_run_rejects_dirty_candidate_before_lock(monkeypatch):
 monkeypatch.setattr(t05,'git_checked',lambda:(_ for _ in ()).throw(RuntimeError('dirty candidate')))
 monkeypatch.setattr(t05,'lock',lambda _:pytest.fail('must not acquire GPU lock'))
 with pytest.raises(RuntimeError,match='dirty candidate'):t05.run()

def test_start_cleanup_failure_retains_owned_process(monkeypatch,tmp_path):
 proc=SimpleNamespace(pid=123)
 monkeypatch.setattr(t05.subprocess,'Popen',lambda *a,**k:proc)
 def failed_stop(_):raise RuntimeError('cannot stop owned service')
 monkeypatch.setattr(t05,'lifecycle',lambda:SimpleNamespace(process_identity=lambda _:None,stop_owned_process=failed_stop))
 with pytest.raises(RuntimeError,match='cannot stop owned service') as caught:t05.start(tmp_path,34567)
 assert caught.value.owned_process is proc

def test_run_keeps_lock_when_failed_start_group_survives(monkeypatch,tmp_path):
 proc=SimpleNamespace(pid=123)
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 proof=tmp_path/'proof';proof.write_text('{}')
 monkeypatch.setattr(t05,'require_kept',lambda _:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'round')
 monkeypatch.setattr(t05,'RUNS',tmp_path/'runs')
 monkeypatch.setattr(t05,'TRACE',proof)
 monkeypatch.setattr(t05,'TRACE_SHA',__import__('hashlib').sha256(proof.read_bytes()).hexdigest())
 monkeypatch.setattr(t05,'lock',lambda _:{'batch':90})
 monkeypatch.setattr(t05,'unlock',lambda _:pytest.fail('live group must retain lock'))
 monkeypatch.setattr(t05.subprocess,'check_output',lambda *a,**k:'0\n')
 monkeypatch.setattr(t05,'port',lambda:34567)
 def failed_stop(_):raise RuntimeError('cannot stop owned service')
 api=SimpleNamespace(verified_module=lambda *a:SimpleNamespace(next_batch=lambda _:90),stop_owned_process=failed_stop,owned_group_alive=lambda _:True)
 monkeypatch.setattr(t05,'lifecycle',lambda:api)
 monkeypatch.setattr(t05,'d07_helpers',lambda:SimpleNamespace(require_child_receipt=lambda *a,**k:None,require_t20_failed_harness=lambda:proof,require_closed_round=lambda *_:proof))
 monkeypatch.setattr(t05,'run_d06_g3g4',lambda _:{})
 monkeypatch.setattr(t05,'archive_sources',lambda _:[])
 def failed_start(*a):
  error=RuntimeError('startup cleanup failed');error.owned_process=proc;raise error
 monkeypatch.setattr(t05,'start',failed_start)
 with pytest.raises(RuntimeError,match='GPU lock preserved'):t05.run(owned_child=True,batch=90,launch_receipt=proof)
 assert (tmp_path/'round'/'failed_harness.json').is_file()
 assert not list((tmp_path/'runs').glob('*/owned_cleanup.json'))

def test_default_cpu_does_not_allocate_or_launch(monkeypatch):
 monkeypatch.setattr(t05,'lifecycle',lambda:pytest.fail('CPU preparation must not allocate a batch'))
 assert t05.main([])==0

def test_d06_failed_start_keeps_original_process_on_cleanup_error(monkeypatch,tmp_path):
 proc=SimpleNamespace(pid=123)
 def start(*args):
  error=RuntimeError('startup failed');error.owned_process=proc;raise error
 def stop(p):
  assert p is proc
  raise RuntimeError('D06 stop failed')
 monkeypatch.setattr(t05,'port',lambda:34567)
 monkeypatch.setattr(t05,'d06_module',lambda:SimpleNamespace(start_server=start,load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=stop)))
 with pytest.raises(RuntimeError,match='D06 stop failed') as caught:t05.run_d06_g3g4(tmp_path/'g3g4')
 assert caught.value.owned_process is proc and caught.value.owned_cleanup_failed

def test_d06_cleanup_exception_retains_outer_lock_even_if_group_check_false(monkeypatch,tmp_path):
 proof=tmp_path/'proof';proof.write_text('{}')
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 monkeypatch.setattr(t05,'require_kept',lambda _:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'E2-R045')
 monkeypatch.setattr(t05,'TRACE',proof)
 monkeypatch.setattr(t05,'TRACE_SHA',__import__('hashlib').sha256(proof.read_bytes()).hexdigest())
 monkeypatch.setattr(t05,'d07_helpers',lambda:SimpleNamespace(require_child_receipt=lambda *a,**k:None,require_t20_failed_harness=lambda:proof,require_closed_round=lambda *_:proof))
 monkeypatch.setattr(t05,'lock',lambda _:{'batch':90})
 monkeypatch.setattr(t05,'unlock',lambda _:pytest.fail('uncertain cleanup must preserve lock'))
 monkeypatch.setattr(t05.subprocess,'check_output',lambda *a,**k:'0\n')
 monkeypatch.setattr(t05,'lifecycle',lambda:SimpleNamespace(owned_group_alive=lambda _:False))
 monkeypatch.setattr(t05,'archive_sources',lambda _:[])
 def failed_d06(path):
  assert path==t05.ROUND/'g3g4'
  error=RuntimeError('D06 stop failed');error.owned_process=SimpleNamespace(pid=123);error.owned_cleanup_failed=True;raise error
 monkeypatch.setattr(t05,'run_d06_g3g4',failed_d06)
 with pytest.raises(RuntimeError,match='cleanup failed; GPU lock preserved'):t05.run(owned_child=True,batch=90,launch_receipt=proof)
 assert __import__('json').loads((t05.ROUND/'owned_cleanup.json').read_text())['lock_released'] is False

def test_child_receipt_rejected_before_candidate_or_lock(monkeypatch,tmp_path):
 def reject(*a,**k):raise RuntimeError('wrong child binding')
 monkeypatch.setattr(t05,'d07_helpers',lambda:SimpleNamespace(require_child_receipt=reject))
 monkeypatch.setattr(t05,'git_checked',lambda:pytest.fail('receipt must precede candidate and GPU checks'))
 monkeypatch.setattr(t05,'lock',lambda _:pytest.fail('invalid child must not take GPU lock'))
 with pytest.raises(RuntimeError,match='wrong child binding'):
  t05.run(owned_child=True,batch=72,launch_receipt=tmp_path/'wrong.json')

@pytest.mark.parametrize('collision',[False,True])
def test_controller_reserves_atomic_batch_and_binds_child(monkeypatch,tmp_path,collision):
 proof=tmp_path/'proof.json';proof.write_text('{}')
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 monkeypatch.setattr(t05,'require_kept',lambda _:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'round')
 monkeypatch.setattr(t05,'LOCK',tmp_path/'gpu.lock')
 monkeypatch.setattr(t05,'RUNS',tmp_path/'runs')
 monkeypatch.setattr(t05,'lock',lambda _:pytest.fail('controller must not own GPU lock'))
 seen={}
 def reserve(helper,batch,rid,argv,path,packet):
  assert batch==72 and rid==t05.RID and '--owned-child' in argv
  assert packet['argv_sha256']=='argv-pin' and packet['candidate_commit']==t05.CANDIDATE
  assert set(packet['prerequisites'])=={'E2-R041-gate-D17','E2-R040','E2-R040e','D16_failed_metadata_only','R055_failed_metadata_only','combined_d06_g3g4'}
  assert packet['prerequisites']['D16_failed_metadata_only']['metadata_only'] is True
  assert packet['section10_basis']['r055_gate_ended'] is True
  seen['reserved']=True
  if collision:raise FileExistsError('batch already reserved')
  return {**packet,'state':'launched','batch_pid':222}
 owned=SimpleNamespace(verified_module=lambda *a:SimpleNamespace(next_batch=lambda _:72),reserve_process=reserve,process_identity=lambda _: {'pid':222,'start_ticks':123})
 def publish(path,receipt,child,**kw):
  assert child=={'pid':222,'start_ticks':123,'execution_id':'222:123'} and kw['lifecycle'] is owned
  return {**receipt,'child':child}
 shared=SimpleNamespace(require_t20_failed_harness=lambda:proof,require_closed_round=lambda *_:proof,argv_sha256=lambda _: 'argv-pin',process_birth=lambda:{'pid':111,'start_ticks':99},publish_child_binding=publish)
 monkeypatch.setattr(t05,'d07_helpers',lambda:shared)
 monkeypatch.setattr(t05,'lifecycle',lambda:owned)
 if collision:
  with pytest.raises(FileExistsError,match='already reserved'):t05.run()
 else:
  result=t05.run();assert result['batch']==72 and result['child']['pid']==222
 assert seen['reserved']

@pytest.mark.parametrize('wrong_batch_pid',[False,True])
def test_real_shared_receipt_reader_accepts_t05_and_rejects_wrong_process(monkeypatch,tmp_path,wrong_batch_pid):
 shared=t05.d07_helpers();birth={'pid':222,'start_ticks':123,'execution_id':'222:123'}
 monkeypatch.setattr(shared,'process_birth',lambda:birth)
 receipt=tmp_path/'launch.json';argv=t05.child_argv(72,receipt)
 receipt.write_text(__import__('json').dumps({'schema':'ft_t05_owned_launch/v1','state':'launched','rid':t05.RID,'batch':72,'candidate_commit':t05.CANDIDATE,'batch_pid':333 if wrong_batch_pid else 222,'child':birth,'argv_sha256':shared.argv_sha256(argv)}))
 if wrong_batch_pid:
  with pytest.raises(RuntimeError,match='binding differs'):
   shared.require_child_receipt(receipt,72,t05.WT,t05.RUNS,rid=t05.RID,expected_argv=argv,schema='ft_t05_owned_launch/v1')
 else:
  checked=shared.require_child_receipt(receipt,72,t05.WT,t05.RUNS,rid=t05.RID,expected_argv=argv,schema='ft_t05_owned_launch/v1');assert checked['rid']==t05.RID


def test_commands_use_only_bound_trace_input(tmp_path):
 trace=tmp_path/'trace_input.json'
 for cmd in t05.commands(tmp_path,34567,trace=trace):
  if '--trace' in cmd:assert cmd[cmd.index('--trace')+1]==str(trace)

def test_changed_retained_trace_rejected_before_service(monkeypatch,tmp_path):
 proof=tmp_path/'proof';proof.write_text('{}');released=[]
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 monkeypatch.setattr(t05,'require_kept',lambda _:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'E2-R045');monkeypatch.setattr(t05,'TRACE',proof)
 monkeypatch.setattr(t05,'d07_helpers',lambda:SimpleNamespace(require_child_receipt=lambda *a,**k:None,require_t20_failed_harness=lambda:proof,require_closed_round=lambda *_:proof))
 monkeypatch.setattr(t05,'lock',lambda _:{'batch':90});monkeypatch.setattr(t05,'unlock',lambda _:released.append(True))
 monkeypatch.setattr(t05.subprocess,'check_output',lambda *a,**k:'0\n')
 monkeypatch.setattr(t05,'run_d06_g3g4',lambda _:pytest.fail('changed input must precede all services'))
 with pytest.raises(RuntimeError,match='registered SHA'):t05.run(owned_child=True,batch=90,launch_receipt=proof)
 assert released==[True] and not t05.ROUND.exists()



def test_eff_binding_and_precise_r055_receipt_source():
 assert t05.CANDIDATE=='effb9969706922ddad9e59b96377e46469ebe97f'
 assert t05.WT.name=='e2base1-p1'
 assert "require_closed_round('E2-R055a-gate-D06','kept')" not in Path(t05.__file__).read_text()
 assert "require_closed_round('E2-R055b-gate-D06','failed_harness')" in Path(t05.__file__).read_text()


def test_failed_d16_metadata_cannot_substitute_for_r040e_measurement(monkeypatch,tmp_path):
 proof=tmp_path/'proof.json';proof.write_text('{}')
 calls=[]
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 monkeypatch.setattr(t05,'require_kept',lambda _:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'round')
 monkeypatch.setattr(t05,'RUNS',tmp_path/'runs')
 monkeypatch.setattr(t05,'LOCK',tmp_path/'lock')
 monkeypatch.setattr(t05,'r055_failed_metadata',lambda:{'r055_gate_ended':True})
 monkeypatch.setattr(t05,'d16_failed_metadata',lambda:{'metadata_only':True,'rounds':{'E2-R040a':{},'E2-R040c':{}}})
 def closed(rid,verdict):
  calls.append((rid,verdict))
  if rid=='E2-R040e':raise RuntimeError('E2-R040e formal D04 verdict is not measured')
  return proof
 shared=SimpleNamespace(require_t20_failed_harness=lambda:proof,require_closed_round=closed)
 monkeypatch.setattr(t05,'d07_helpers',lambda:shared)
 monkeypatch.setattr(t05,'lock',lambda _:pytest.fail('missing R040e must precede lock'))
 with pytest.raises(RuntimeError,match='E2-R040e'):
  t05.run()
 assert calls==[('E2-R040e','measured')]


def test_dry_run_creates_shared_formal_paths_without_service_or_lock(monkeypatch,tmp_path):
 trace=tmp_path/'trace.json';trace.write_text('{"small":"business input"}')
 monkeypatch.setattr(t05,'ROUND',tmp_path/'E2-R045');monkeypatch.setattr(t05,'TRACE',trace);monkeypatch.setattr(t05,'TRACE_SHA',t05.sha(trace))
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 monkeypatch.setattr(t05,'source_hashes',lambda:{str(tmp_path/'source.py'):'s'*64})
 def copied(source,target):target.write_text('source');return {'source':str(source),'source_sha256':'s'*64,'copy':str(target),'copy_sha256':t05.sha(target),'mode':'0o600'}
 monkeypatch.setattr(t05,'copy_runtime',copied)
 monkeypatch.setattr(t05.subprocess,'Popen',lambda *_:pytest.fail('dry run must not Popen'))
 monkeypatch.setattr(t05.urllib.request,'urlopen',lambda *_:pytest.fail('dry run must not connect'))
 row=t05.dry_run();target=t05.dry_run_directory()
 assert row['formal_rid_directory_created'] is False and (target/'g3g4/g3.json').is_file()
 for arm in ('P1','P2'):
  assert (target/arm/'ENV.txt').read_text() and (target/arm/'SERVE_CMD.txt').is_file()
  assert all((target/arm/name).is_file() for name in ('first_shot.json','a_two_decode_diff.json','a_two_decode_same.json','b_stall_cold32k.json','b_stall_agent.json','c_pair_short.json'))
  assert (target/f'{arm}_h1_diagnostic/d_h1.json').is_file()
 assert not (tmp_path/'E2-R045').exists()
 observer=(target/'g3g4/d06_pause_observer_v3.py').read_text()
 assert 'elif name=="UserMsg":' in observer and row['harness_version']=='r045-section14-v11'
 assert (target/'g3g4/pause_cancel.json').is_file() and (target/'g3g4/after_cancel.json').is_file()


def test_env_whitelist_excludes_injected_secret(monkeypatch,tmp_path):
 monkeypatch.setenv('FT_SSH_PASSWORD','not-for-artifacts')
 t05.prepare_service_files(tmp_path,34567,file_dry_run=True)
 assert 'not-for-artifacts' not in (tmp_path/'ENV.json').read_text()
 assert 'not-for-artifacts' not in (tmp_path/'ENV.txt').read_text()
 assert 'not-for-artifacts' not in (tmp_path/'SERVE_CMD.txt').read_text()


def test_start_writes_real_parsed_arguments_after_health(monkeypatch,tmp_path):
 proc=SimpleNamespace(pid=12,poll=lambda:None)
 life=SimpleNamespace(process_identity=lambda _: {'pid':12,'pgid':12,'session':12},stop_owned_process=lambda _:None)
 def popen(*args,**kwargs):
  kwargs['stdout'].write('Parsed arguments\nServerArgs(server_port=34567)\n');kwargs['stdout'].flush();return proc
 class Health:
  def __enter__(self):return self
  def __exit__(self,*_):return False
  def read(self):return b'{"status":"ok"}'
 monkeypatch.setattr(t05,'lifecycle',lambda:life);monkeypatch.setattr(t05.subprocess,'Popen',popen);monkeypatch.setattr(t05.urllib.request,'urlopen',lambda *_,**__:Health())
 assert t05.start(tmp_path,34567) is proc
 assert 'ServerArgs' in (tmp_path/'serve_args.txt').read_text() and json.loads((tmp_path/'health.json').read_text())['status']=='ok'


def test_actual_r045_d06_calls_pause_chain_before_owned_cleanup(monkeypatch,tmp_path):
 events=[];proc=SimpleNamespace(pid=123)
 def chain(directory,worktree,port):
  assert events==['start','two-decode','h1'];events.append('pause/cancel/resume');return {'complete':True}
 d=SimpleNamespace(PROBE=Path('scripts/multisession_probe.py'),start_server=lambda *a:(events.append('start') or proc),
    environment=lambda *a:{},validate_g3=lambda _: {'g3':'valid'},validate_g4=lambda *a:{'g4':'valid'},run_pause_chain=chain,
    load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda _:events.append('stop')))
 def client(argv,**kw):
  events.append(argv[2]);Path(argv[argv.index('--out')+1]).write_text(json.dumps({'reps':[{'idle':{}},{'idle':{}},{'idle':{}}]}))
 monkeypatch.setattr(t05,'d06_module',lambda:d);monkeypatch.setattr(t05.subprocess,'run',client)
 result=t05.run_d06_g3g4(tmp_path/'g3g4')
 assert events==['start','two-decode','h1','pause/cancel/resume','stop']
 assert result['pause_chain']['complete'] is True and result['memory_ratio']==0.88


def test_ordinary_card_splits_d0_only_h1_from_performance_lock(monkeypatch):
 REAL_ORDINARY_CAPABILITY()
 plan=t05.suite_plan(Path('/tmp/t05'))
 assert {row['kind'] for row in plan[:-1]}=={'ordinary_two_decode','ordinary_stall','ordinary_pair_short'}
 assert plan[-1]['kind']=='d06_diagnostic_only' and 'pause endpoint' in plan[-1]['reason']

def test_actual_ordinary_adapter_binds_normal_sse_to_worker_token_sidecars(monkeypatch,tmp_path):
 payload=tmp_path/'input.json';payload.write_text(json.dumps({'model':'m','messages':[{'role':'user','content':'x'}],'stream':True,'stream_options':{'include_usage':True}}))
 raw=(
  'data: {"id":"chatcmpl-7","choices":[{"delta":{"content":"x"},"finish_reason":null}]}\n'
  'data: {"id":"chatcmpl-7","choices":[{"delta":{},"finish_reason":"length"}],"usage":{"prompt_tokens":2,"completion_tokens":2}}\n'
  'data: [DONE]\n').encode()
 class Response:
  def __enter__(self):return self
  def __exit__(self,*_):return False
  def __iter__(self):return iter(raw.splitlines(keepends=True))
 adapter=t05.ordinary_adapter();observed=[]
 monkeypatch.setattr(adapter.urllib.request,'urlopen',lambda request,timeout:Response())
 api=tmp_path/'api.json';adapter.ordinary_stream_request('http://127.0.0.1:41877/v1',payload,api,on_first_real=lambda uid,event:observed.append((uid,event)))
 assert observed and observed[0][0]==7 and type(observed[0][1]['monotonic_ns']) is int
 birth={'pid':1,'start_ticks':2,'execution_id':'1:2','pgid':1,'session':1}
 ids=tmp_path/'ids.json';ids.write_bytes(b'[11,12]')
 digest=__import__('hashlib').sha256(ids.read_bytes()).hexdigest()
 inputs=tmp_path/'inputs.jsonl';inputs.write_text(json.dumps({'schema':'ft_t06_ordinary_input/v3','uid':7,'service_birth':birth,'worker_birth':birth,'canonical_encoding':'utf8-json-int-array-separators=,:','input_tokens':2,'input_ids_sha256':digest,'input_ids_path':str(ids),'input_ids_file_sha256':digest,'source':'Scheduler._process_one_msg(UserMsg)','time_ns':1})+'\n')
 tokens=tmp_path/'tokens.jsonl';tokens.write_text('\n'.join(json.dumps({'schema':'ft_t06_ordinary_token/v3','uid':7,'service_birth':birth,'worker_birth':birth,'request_seq':i,'completion_tokens_delta':1,'completion_tokens_cumulative':i,'next_token':100+i,'finished':i==2,'finish_reason':'length' if i==2 else None,'time_ns':10+i}) for i in (1,2))+'\n')
 binding=t05.ordinary_client().bind(payload,api,None,None,inputs,tokens,tmp_path/'binding.json')
 value=adapter.ordinary_binding(binding)
 assert value['uid']==7 and value['input_tokens']==2 and value['completion_tokens']==2 and value['finish_reason']=='length'

def test_actual_h1_diagnostic_uses_d06_environment_and_three_reps(monkeypatch,tmp_path):
 seen={}
 class D06:
  PROBE=Path('scripts/multisession_probe.py')
  def environment(self,worktree,d0):
   seen['environment']=(worktree,d0);return {'D06':'1'}
  def validate_g4(self,value,log):
   seen.setdefault('validated',[]).append((value,log));return {'validated_h1':True}
 monkeypatch.setattr(t05,'d06_module',lambda:D06())
 def fake_run(argv,**kwargs):
  seen['argv']=argv;seen['kwargs']=kwargs;Path(argv[argv.index('--out')+1]).write_text(json.dumps({'reps':[{'idle':{}},{'idle':{}},{'idle':{}}]}))
 monkeypatch.setattr(t05.subprocess,'run',fake_run)
 value=t05.run_t05_h1_diagnostic(tmp_path,t05.WT,45678)
 assert seen['argv'][2]=='h1' and seen['argv'][seen['argv'].index('--reps')+1]=='3'
 assert seen['argv'][seen['argv'].index('--H')+1]=='1,8,32'
 assert seen['kwargs']['env']=={'D06':'1'} and value['performance_numeric_reuse_forbidden'] is True and len(seen['validated'])==3 and all(len(item[0]['reps'])==1 for item in seen['validated'])

def test_stall_decode_reader_continues_while_prefill_transport_blocks(monkeypatch,tmp_path):
 inputs=tmp_path/'ordinary_observer';inputs.mkdir();(inputs/'tokens.jsonl').write_text(json.dumps({'uid':7,'time_ns':15,'next_token':1})+'\n')
 release=__import__('threading').Event();prefill_entered=__import__('threading').Event();decode_finished=__import__('threading').Event()
 digest=__import__('hashlib').sha256(b'[]').hexdigest()
 def record(uid,first,last):return {'uid':uid,'input_ids_sha256':digest,'input_tokens':0,'prompt_tokens':0,'completion_tokens':len([first,last]),'token_events':[{'time_ns':first,'next_token':1},{'time_ns':last,'next_token':2}],'evidence':{'worker_input':{'time_ns':first-5}}}
 class Adapter:
  def ordinary_stream_request(self,base,input_path,out,timeout=1800,on_first_real=None):
   if str(input_path).endswith('.decode.input.json'):
    on_first_real(7,{'time_ns':11,'monotonic_ns':21});decode_finished.set();return {}
   prefill_entered.set();assert decode_finished.is_set();release.wait(2);return {}
  def ordinary_binding(self,binding):return binding
 class Client:
  def bind(self,*args):return record(7,20,30) if str(args[0]).endswith('.decode.input.json') else record(8,40,50)
 monkeypatch.setattr(t05,'ordinary_adapter',lambda:Adapter());monkeypatch.setattr(t05,'ordinary_client',lambda:Client())
 result=[]
 worker=__import__('threading').Thread(target=lambda:result.append(t05.run_stall_ordinary(tmp_path,45678,name='stall',prefill_messages=[],decode_messages=[],decode_ids=[],prefill_ids=[],reps=1,delay_s=0)));
 worker.start();assert prefill_entered.wait(2) and decode_finished.is_set();release.set();worker.join(3)
 assert not worker.is_alive() and result and result[0]['reps'][0]['sc2']['max_decode_gap_ns']==10

def test_h1_three_reps_call_real_d06_validator_per_rep(monkeypatch,tmp_path):
 real=t05.d06_module();base=tmp_path/'d0';(tmp_path/'d0_decode_steps.jsonl').write_text(json.dumps({'t':1})+'\n');(tmp_path/'d0_prefill.jsonl').write_text(json.dumps({'t_start':1,'t_end':2})+'\n')
 (tmp_path/'serve.log').write_text('[2026-01-01|00:00:00|engine] Decode batch\n')
 start=__import__('datetime').datetime(2026,1,1,0,0,10).timestamp();end=start+2
 rep={'idle':{'event':{'event_start_wallclock_s':start,'event_end_wallclock_s':end,'pause':{'response':{'pause_started_wallclock_s':start,'deadline_wallclock_s':end}}},'evidence':{'d0_base':str(base),'event_counters':{'steps':[]}}}}
 monkeypatch.setattr(real,'environment',lambda *_:{'D06':'1'});monkeypatch.setattr(t05,'d06_module',lambda:real)
 def emit(argv,**kwargs):Path(argv[argv.index('--out')+1]).write_text(json.dumps({'schema':'multisession_probe/v1','command':'h1','reps':[rep,rep,rep]}))
 monkeypatch.setattr(t05.subprocess,'run',emit)
 value=t05.run_t05_h1_diagnostic(tmp_path,t05.WT,45678)
 assert len(value['per_rep_validator'])==3 and all(item['validator']['d0_steps_checked']==1 for item in value['per_rep_validator'])

def test_dry_plan_uses_ordinary_outputs_not_candidate_probe_commands(tmp_path):
 rows=t05.dry_workloads(tmp_path,45678,tmp_path/'trace.json')
 assert any('first_shot.json' in row['path'] for row in rows)
 assert not any('multisession_probe' in row['purpose'] for row in rows)
 assert any('ordinary request input' in row['purpose'] for row in rows)
 paths={Path(row['path']).name for row in rows}
 assert {'b_stall_cold32k.rep2.decode.api.sse','b_stall_cold32k.rep2.prefill.binding.json','c_pair_short.rep2.left.api.events.jsonl','sc3_prefill_evidence.json','sc5_timeline.json'}<=paths

def test_source_inventory_archives_actual_repair_dependencies(monkeypatch,tmp_path):
 wt=Path(__file__).parents[1]/'e2r046_pausefix'
 if not wt.is_dir():wt=Path('/data2/FreeToken/wt/e2base1-p1')
 monkeypatch.setattr(t05,'WT',wt)
 helper_source=tmp_path/'helpers-source';raw=helper_source/'helpers/raw';raw.mkdir(parents=True)
 for name in ('cold_eq.py','probe_ft_cold32k.py'):
  (raw/name).write_bytes((Path(__file__).parents[1]/'t16_frozen_helpers_v1'/name).read_bytes())
 monkeypatch.setattr(t05,'OWNED_SOURCE',helper_source)
 hashes=t05.source_hashes();names={Path(name).name for name in hashes}
 assert {'r055b_pause_harness_v2.py','r055b_owned_launch.py','r055_owned_launch.py','d06_g3g4_prepare.py'}<=names
 rows=t05.archive_sources(tmp_path/'source_tools')
 assert len(rows)==len(hashes) and all(row['source_sha256']==row['copy_sha256'] for row in rows)
 assert (tmp_path/'source_tools/r055b_pause_harness_v2.py').is_file()
 assert (tmp_path/'source_tools/d04_original/serve_args_diff.py').is_file()
 assert (tmp_path/'source_tools/cold_helpers/cold_eq.py').is_file()
 assert REAL_VERIFY_PAUSE_HELPERS()['cold_eq_raw_sha256']=='1fe95158522da413621e58187c0198f26cf5860b64e3d74dd76df8cfb75a6093'


def test_t05_real_service_writer_keeps_98304_088_and_disables_d0_trace(monkeypatch,tmp_path):
 monkeypatch.setenv('FT_DEV_D0','1');monkeypatch.setenv('FT_DEV_ROUTE_TRACE','1')
 env,argv=t05.prepare_service_files(tmp_path,51449,file_dry_run=True)
 assert json.loads((tmp_path/'serve_argv.json').read_text())['argv']==argv
 assert argv[0].endswith('python') and Path(argv[1]).name=='r046c_t06_ordinary_startup_v4.py' and argv[2]=='--observer-dir'
 assert argv[argv.index('--kv-reserve-tokens')+1]=='98304'
 assert argv[argv.index('--memory-ratio')+1]=='0.88'
 assert not any(key.startswith('FT_DEV_D0') or key=='FT_DEV_ROUTE_TRACE' for key in env)
 assert '--route-trace' not in argv and '--enable-route-trace' not in argv
 assert 'R055B_MODEL_MEMORY' not in env and 'R055_PAUSE_OBSERVATIONS' not in env
 assert not (tmp_path/'d06_pause_observer_v3.py').exists()



def test_t05_uses_ftd_forward_trace_sha_and_rejects_reverse_binding(monkeypatch,tmp_path):
 assert t05.TRACE==Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json')
 assert t05.TRACE_SHA=='055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899'
 trace=tmp_path/'trace_rev.json';trace.write_text('{"rounds":[]}')
 monkeypatch.setattr(t05,'TRACE',trace);monkeypatch.setattr(t05,'ROUND',tmp_path/'E2-R045')
 monkeypatch.setattr(t05,'git_checked',lambda:{'commit':t05.CANDIDATE})
 monkeypatch.setattr(t05,'archive_sources',lambda _:pytest.fail('wrong input must precede source/output copy'))
 with pytest.raises(RuntimeError,match='FTD T2 trace.json registered SHA'):t05.dry_run()
 assert not (t05.dry_run_directory()/'trace_input.json').exists()

@pytest.mark.parametrize('old_schema',['v6','v7','v8'])
def test_v11_dry_receipt_rejects_every_prior_schema(monkeypatch,tmp_path,old_schema):
 monkeypatch.setattr(t05,'ROUND',tmp_path/'E2-R045');monkeypatch.setattr(t05,'source_hashes',lambda:{'source':'sha'})
 directory=t05.dry_run_directory();directory.mkdir();assert directory.name=='.dryrun_R045_section14_v11_E2-R045'
 row={'schema':f'ft_r045_dry_run/{old_schema}','harness_version':t05.HARNESS_VERSION,'rid':t05.RID,'candidate_commit':t05.CANDIDATE,'parent_commit':t05.PARENT,'passed':True,'source_sha256':t05.source_hashes(),'owner':{'path':str(Path(t05.__file__).resolve()),'uid':getattr(t05.os,'getuid',lambda:None)(),'user':t05.os.environ.get('USER') or t05.os.environ.get('LOGNAME')},'cwd':str(t05.ROOT),'worktree':{'path':str(t05.WT),'parent':str(t05.WT.parent)}}
 row.update({k:False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated')})
 path=directory/'dry_run_receipt.json';path.write_text(json.dumps(row));path.chmod(0o444)
 try:
  with pytest.raises(RuntimeError,match='identity differs'):REAL_DRY_RECEIPT()
 finally:path.chmod(0o600)

@pytest.mark.parametrize('old_schema',['v6','v7','v8'])
def test_v11_startup_review_rejects_every_prior_schema(monkeypatch,tmp_path,old_schema):
 monkeypatch.setattr(t05,'RUNS',tmp_path);monkeypatch.setattr(t05,'source_hashes',lambda:{'source':'sha'})
 receipt={'path':'dry','sha256':'d'*64};path=tmp_path/'reviews/E2-R045_section14_startup_review_v11.json';path.parent.mkdir()
 row={'schema':f'ft_r045_startup_review/{old_schema}','harness_version':t05.HARNESS_VERSION,'rid':t05.RID,'candidate_commit':t05.CANDIDATE,'parent_commit':t05.PARENT,'approved':True,'verdict':'PASS','source_sha256':t05.source_hashes(),'dry_run_receipt':receipt['path'],'dry_run_receipt_sha256':receipt['sha256']}
 path.write_text(json.dumps(row));path.chmod(0o444)
 try:
  with pytest.raises(RuntimeError,match='binding differs'):REAL_STARTUP_REVIEW(receipt)
 finally:path.chmod(0o600)

def test_d16_retained_closures_bind_six_anchor_and_case_metadata(monkeypatch, tmp_path):
    rounds = tmp_path / 'rounds'
    rows = {}
    for rid in ('E2-R040a', 'E2-R040c', 'E2-R040d'):
        directory = rounds / rid
        directory.mkdir(parents=True)
        round_path = directory / 'round.json'
        round_path.write_text(json.dumps({'round_id': rid, 'verdict': 'failed_harness'}))
        manifest = directory / 'MANIFEST.sha256'
        manifest.write_text(f'bound {rid}\n')
        rows[rid] = round_path

    shared = SimpleNamespace(require_closed_round=lambda rid, verdict: rows[rid] if verdict == 'failed_harness' else pytest.fail('wrong verdict'))
    monkeypatch.setattr(t05, 'd07_helpers', lambda: shared)
    value = REAL_D16_METADATA()

    assert value['metadata_only'] is True
    assert value['performance_reuse_forbidden'] is True
    assert value['retained_anchor_count'] == 6
    assert value['retained_case_count'] == 6
    assert {rid: item['retained_scope'] for rid, item in value['rounds'].items()} == {
        'E2-R040a': 'six_anchors',
        'E2-R040c': 'six_cases',
        'E2-R040d': 'failed_measurement',
    }


def test_future_r040e_gate_is_not_satisfied_by_any_retained_failure(monkeypatch, tmp_path):
    proof = tmp_path / 'proof.json'
    proof.write_text('{}')
    calls = []
    monkeypatch.setattr(t05, 'git_checked', lambda: {'commit': t05.CANDIDATE})
    monkeypatch.setattr(t05, 'require_kept', lambda _: proof)
    monkeypatch.setattr(t05, 'ROUND', tmp_path / 'round')
    monkeypatch.setattr(t05, 'RUNS', tmp_path / 'runs')
    monkeypatch.setattr(t05, 'LOCK', tmp_path / 'gpu.lock')
    monkeypatch.setattr(t05, 'r055_failed_metadata', lambda: {'r055_gate_ended': True})
    monkeypatch.setattr(t05, 'd16_failed_metadata', lambda: {'metadata_only': True, 'rounds': {'E2-R040a': {}, 'E2-R040c': {}, 'E2-R040d': {}}})
    def closed(rid, verdict):
        calls.append((rid, verdict))
        if rid == 'E2-R040e':
            raise RuntimeError('E2-R040e formal D04 verdict is not measured')
        return proof
    monkeypatch.setattr(t05, 'd07_helpers', lambda: SimpleNamespace(require_t20_failed_harness=lambda: proof, require_closed_round=closed))
    monkeypatch.setattr(t05, 'lock', lambda _: pytest.fail('future D16 gate must precede lock'))

    with pytest.raises(RuntimeError, match='E2-R040e'):
        t05.run()
    assert calls == [('E2-R040e', 'measured')]


def test_v9_source_copy_is_private_writable_after_copyfile(tmp_path):
    source = tmp_path / 'sealed.py'
    source.write_text('x = 1\n')
    source.chmod(0o444)
    target = tmp_path / 'runtime.py'
    row = t05.copy_runtime(source, target)
    assert target.read_text() == source.read_text()
    assert row['copy_sha256'] == row['source_sha256']
    target.write_text('x = 2\\n')
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600
    assert row['source_sha256'] == row['copy_sha256']
