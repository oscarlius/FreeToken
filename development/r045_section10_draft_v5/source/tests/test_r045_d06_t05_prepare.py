import importlib.util, json
from pathlib import Path
import pytest
from types import SimpleNamespace

SPEC=importlib.util.spec_from_file_location('t05',Path(__file__).parents[1]/'r045_d06_t05_prepare.py');t05=importlib.util.module_from_spec(SPEC);assert SPEC.loader;SPEC.loader.exec_module(t05)
REAL_VERIFY_PAUSE_HELPERS=t05.verify_pause_helpers
REAL_DRY_RECEIPT=t05.require_dry_run_receipt
REAL_STARTUP_REVIEW=t05.require_startup_review
@pytest.fixture(autouse=True)
def _receipt_gate(monkeypatch):
 monkeypatch.setattr(t05,'require_dry_run_receipt',lambda:{'path':'dry-receipt','sha256':'d'*64})
 monkeypatch.setattr(t05,'require_startup_review',lambda receipt:{'path':'startup-review','sha256':'r'*64})
 monkeypatch.setattr(t05,'r055_failed_metadata',lambda:{'r055_gate_ended':True,'r055c_authorized':False,'default_path':{'partial_cold_verdict':'PASS'}})
 monkeypatch.setattr(t05,'verify_pause_helpers',lambda:{'test_double':True})
 class OfflineSocket:
  def __enter__(self):return self
  def __exit__(self,*_):return False
  def bind(self,address):assert address==('127.0.0.1',0)
  def getsockname(self):return ('127.0.0.1',51449)
  def connect(self,*_):pytest.fail('CPU socket guard rejects connect')
 monkeypatch.setattr(t05.socket,'socket',lambda *a,**k:OfflineSocket())
 monkeypatch.setattr(t05.urllib.request,'urlopen',lambda *a,**k:pytest.fail('offline CPU tests must not send HTTP'))
def test_cpu_command_shape_keeps_card_contract():
 c=t05.commands(Path('/tmp/t05'),34567)
 assert len(c)==6
 assert c[0][2]=='two-decode' and c[0].index('--base-url')>2
 assert all('8095' not in item for row in c for item in row)
 assert c[0][c[0].index('--same-prompt')+1]=='0' and c[0][c[0].index('--reps')+1]=='3'
 assert c[1][c[1].index('--same-prompt')+1]=='1' and c[1][c[1].index('--reps')+1]=='1'
 assert c[-1][c[-1].index('--H'):c[-1].index('--H')+6]==['--H','1,8,32','--reps','3','--prefill-target','32052']
def test_two_arm_window_and_dynamic_loopback_only():
 argv=t05.serve_argv(45678)
 assert argv[argv.index('--kv-reserve-tokens')+1]=='73728'
 assert argv[argv.index('--max-seq-len-override')+1]=='73728'
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
  assert set(packet['prerequisites'])=={'E2-R041-gate-D17','E2-R040','E2-R040a','R055_failed_metadata_only','combined_d06_g3g4'}
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
  assert all((target/arm/name).is_file() for name in ('first_shot.json','a_two_decode_diff.json','a_two_decode_same.json','b_stall_cold32k.json','b_stall_agent.json','c_pair_short.json','d_h1.json'))
 assert not (tmp_path/'E2-R045').exists()
 observer=(target/'g3g4/d06_pause_observer_v3.py').read_text()
 assert 'elif name=="UserMsg":' in observer and row['harness_version']=='r045-section10-v5'
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
  events.append(argv[2]);Path(argv[argv.index('--out')+1]).write_text('{}')
 monkeypatch.setattr(t05,'d06_module',lambda:d);monkeypatch.setattr(t05.subprocess,'run',client)
 result=t05.run_d06_g3g4(tmp_path/'g3g4')
 assert events==['start','two-decode','h1','pause/cancel/resume','stop']
 assert result['pause_chain']['complete'] is True and result['memory_ratio']==0.88


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


def test_t05_real_service_writer_keeps_73728_and_088(tmp_path):
 env,argv=t05.prepare_service_files(tmp_path,51449,file_dry_run=True)
 assert json.loads((tmp_path/'serve_argv.json').read_text())['argv']==argv
 assert argv[0].endswith('ft') and argv[1]=='serve'
 assert argv[argv.index('--kv-reserve-tokens')+1]=='73728'
 assert argv[argv.index('--memory-ratio')+1]=='0.88'
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

@pytest.mark.parametrize('old_schema',[False,True])
def test_v5_dry_receipt_rejects_v4_schema(monkeypatch,tmp_path,old_schema):
 monkeypatch.setattr(t05,'ROUND',tmp_path/'E2-R045');monkeypatch.setattr(t05,'source_hashes',lambda:{'source':'sha'})
 directory=t05.dry_run_directory();directory.mkdir();assert directory.name=='.dryrun_R045_section10_v5_E2-R045'
 row={'schema':'ft_r045_dry_run/v4' if old_schema else 'ft_r045_dry_run/v5','harness_version':t05.HARNESS_VERSION,'rid':t05.RID,'candidate_commit':t05.CANDIDATE,'parent_commit':t05.PARENT,'passed':True,'source_sha256':t05.source_hashes(),'owner':{'path':str(Path(t05.__file__).resolve()),'uid':getattr(t05.os,'getuid',lambda:None)(),'user':t05.os.environ.get('USER') or t05.os.environ.get('LOGNAME')},'cwd':str(t05.ROOT),'worktree':{'path':str(t05.WT),'parent':str(t05.WT.parent)}}
 row.update({k:False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated')})
 path=directory/'dry_run_receipt.json';path.write_text(json.dumps(row));path.chmod(0o444)
 try:
  if old_schema:
   with pytest.raises(RuntimeError,match='identity differs'):REAL_DRY_RECEIPT()
  else:assert REAL_DRY_RECEIPT()['path']==str(path)
 finally:path.chmod(0o600)

@pytest.mark.parametrize('old_schema',[False,True])
def test_v5_startup_review_rejects_v4_schema(monkeypatch,tmp_path,old_schema):
 monkeypatch.setattr(t05,'RUNS',tmp_path);monkeypatch.setattr(t05,'source_hashes',lambda:{'source':'sha'})
 receipt={'path':'dry','sha256':'d'*64};path=tmp_path/'reviews/E2-R045_section10_startup_review_v5.json';path.parent.mkdir()
 row={'schema':'ft_r045_startup_review/v4' if old_schema else 'ft_r045_startup_review/v5','harness_version':t05.HARNESS_VERSION,'rid':t05.RID,'candidate_commit':t05.CANDIDATE,'parent_commit':t05.PARENT,'approved':True,'verdict':'PASS','source_sha256':t05.source_hashes(),'dry_run_receipt':receipt['path'],'dry_run_receipt_sha256':receipt['sha256']}
 path.write_text(json.dumps(row));path.chmod(0o444)
 try:
  if old_schema:
   with pytest.raises(RuntimeError,match='binding differs'):REAL_STARTUP_REVIEW(receipt)
  else:assert REAL_STARTUP_REVIEW(receipt)['path']==str(path)
 finally:path.chmod(0o600)
