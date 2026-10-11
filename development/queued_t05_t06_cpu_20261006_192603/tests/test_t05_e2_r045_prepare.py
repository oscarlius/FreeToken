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
 def failed_start(*a):
  error=RuntimeError('startup cleanup failed');error.owned_process=proc;raise error
 monkeypatch.setattr(t05,'start',failed_start)
 with pytest.raises(RuntimeError,match='GPU lock preserved'):t05.run()
 assert len(list((tmp_path/'runs').glob('*/failed_harness.json')))==1
 assert not list((tmp_path/'runs').glob('*/owned_cleanup.json'))
