import importlib.util
from pathlib import Path
import pytest
from types import SimpleNamespace

SPEC=importlib.util.spec_from_file_location('t05',Path(__file__).parents[1]/'t05_e2_r045_prepare.py');t05=importlib.util.module_from_spec(SPEC);assert SPEC.loader;SPEC.loader.exec_module(t05)
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
 monkeypatch.setattr(t05,'require_d06',lambda:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'round')
 monkeypatch.setattr(t05,'RUNS',tmp_path/'runs')
 monkeypatch.setattr(t05,'TRACE',proof)
 monkeypatch.setattr(t05,'lock',lambda _:{'batch':90})
 monkeypatch.setattr(t05,'unlock',lambda _:pytest.fail('live group must retain lock'))
 monkeypatch.setattr(t05.subprocess,'check_output',lambda *a,**k:'0\n')
 monkeypatch.setattr(t05,'port',lambda:34567)
 def failed_stop(_):raise RuntimeError('cannot stop owned service')
 api=SimpleNamespace(verified_module=lambda *a:SimpleNamespace(next_batch=lambda _:90),stop_owned_process=failed_stop,owned_group_alive=lambda _:True)
 monkeypatch.setattr(t05,'lifecycle',lambda:api)
 monkeypatch.setattr(t05,'d07_helpers',lambda:SimpleNamespace(require_child_receipt=lambda *a,**k:None))
 def failed_start(*a):
  error=RuntimeError('startup cleanup failed');error.owned_process=proc;raise error
 monkeypatch.setattr(t05,'start',failed_start)
 with pytest.raises(RuntimeError,match='GPU lock preserved'):t05.run(owned_child=True,batch=90,launch_receipt=proof)
 assert len(list((tmp_path/'runs').glob('*/failed_harness.json')))==1
 assert not list((tmp_path/'runs').glob('*/owned_cleanup.json'))

def test_default_cpu_does_not_allocate_or_launch(monkeypatch):
 monkeypatch.setattr(t05,'lifecycle',lambda:pytest.fail('CPU preparation must not allocate a batch'))
 assert t05.main([])==0

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
 monkeypatch.setattr(t05,'require_d06',lambda:proof)
 monkeypatch.setattr(t05,'ROUND',tmp_path/'round')
 monkeypatch.setattr(t05,'LOCK',tmp_path/'gpu.lock')
 monkeypatch.setattr(t05,'RUNS',tmp_path/'runs')
 monkeypatch.setattr(t05,'lock',lambda _:pytest.fail('controller must not own GPU lock'))
 seen={}
 def reserve(helper,batch,rid,argv,path,packet):
  assert batch==72 and rid==t05.RID and '--owned-child' in argv
  assert packet['argv_sha256']=='argv-pin' and packet['candidate_commit']==t05.CANDIDATE
  assert set(packet['prerequisites'])=={'E2-R041-gate-D17','E2-R040','E2-R042_result'}
  seen['reserved']=True
  if collision:raise FileExistsError('batch already reserved')
  return {**packet,'state':'launched','batch_pid':222}
 owned=SimpleNamespace(verified_module=lambda *a:SimpleNamespace(next_batch=lambda _:72),reserve_process=reserve,process_identity=lambda _: {'pid':222,'start_ticks':123})
 def publish(path,receipt,child,**kw):
  assert child=={'pid':222,'start_ticks':123,'execution_id':'222:123'} and kw['lifecycle'] is owned
  return {**receipt,'child':child}
 shared=SimpleNamespace(argv_sha256=lambda _: 'argv-pin',process_birth=lambda:{'pid':111,'start_ticks':99},publish_child_binding=publish)
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
