import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

launcher_path = Path(__file__).resolve().parents[1] / 't16_candidate_launch_d07.py'
if not launcher_path.is_file():
    launcher_path = launcher_path.with_name('t16_candidate_launch.py')
spec = importlib.util.spec_from_file_location('candidate_launcher_d07', launcher_path)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_round_identity_uses_actual_ledger_with_gate_suffixes(tmp_path):
    for name in ('E2-R000', 'E2-R017', 'E2-R013', 'E2-R002-gate-D03', 'batch45.log.tmp'):
        (tmp_path / name).mkdir()
    assert launcher.next_round(tmp_path) == 18


@pytest.mark.parametrize('entries', [[], ['E2-R999'], ['E2-R018-file']])
def test_invalid_or_exhausted_ledger_is_rejected(tmp_path, entries):
    for name in entries:
        if name.endswith('-file'):
            (tmp_path / name).touch()
        else:
            (tmp_path / name).mkdir()
    with pytest.raises(ValueError):
        launcher.next_round(tmp_path)


def test_changed_dependency_is_rejected_before_import(tmp_path):
    path = tmp_path / 'module.py'
    path.write_text('raise AssertionError("untrusted module executed")')
    with pytest.raises(ValueError, match='changed'):
        launcher.verified_module(path, '0' * 64, 'untrusted')


def test_receipt_collision_prevents_process_launch(tmp_path):
    path = tmp_path/'receipt.json'; path.write_text('existing receipt')
    helper = SimpleNamespace(reserve_and_launch=lambda *_: pytest.fail('process started after receipt collision'))
    with pytest.raises(FileExistsError):
        launcher.reserve_process(helper,46,'E2-R018-gate-D03',[],path,{'state':'reserved'})
    assert path.read_text() == 'existing receipt'


def test_receipt_write_failure_prevents_process_launch(monkeypatch,tmp_path):
    helper = SimpleNamespace(reserve_and_launch=lambda *_: pytest.fail('process started before receipt could be written'))
    def failed_write(*_):
        raise OSError('disk full')
    monkeypatch.setattr(launcher,'write_exclusive',failed_write)
    with pytest.raises(OSError,match='disk full'):
        launcher.reserve_process(helper,46,'E2-R018-gate-D03',[],tmp_path/'receipt.json',{'state':'reserved'})


def test_launch_failure_is_retained_in_reserved_receipt(tmp_path):
    def failed_launch(*_):
        raise OSError('injected Popen failure')
    path = tmp_path/'receipt.json'
    with pytest.raises(OSError,match='Popen'):
        launcher.reserve_process(SimpleNamespace(reserve_and_launch=failed_launch),46,'E2-R018-gate-D03',[],path,{'state':'reserved'})
    assert json.loads(path.read_text())['state'] == 'launch_failed'


def test_success_observes_reserved_receipt_before_starting_process(tmp_path):
    path = tmp_path/'receipt.json'
    wrapper = tmp_path/'wrapper.sh'; wrapper.write_text('exec approved command')
    def start(*_):
        assert json.loads(path.read_text())['state'] == 'reserved'
        return SimpleNamespace(pid=123456),wrapper,tmp_path/'batch.log'
    result = launcher.reserve_process(SimpleNamespace(reserve_and_launch=start),46,'E2-R018-gate-D03',[],path,{'state':'reserved'})
    assert result['state'] == 'launched' and result['batch_pid'] == 123456
    assert json.loads(path.read_text()) == result


def test_publish_failure_escalates_term_timeout_to_kill(monkeypatch,tmp_path):
    path = tmp_path/'receipt.json'
    wrapper = tmp_path/'wrapper.sh'; wrapper.write_text('owned wrapper')
    process = SimpleNamespace(pid=123456,poll=lambda:None)
    helper = SimpleNamespace(reserve_and_launch=lambda *_:(process,wrapper,tmp_path/'batch.log'))
    def failed_publish(*_):
        raise OSError('receipt publication failed')
    monkeypatch.setattr(launcher,'publish_receipt',failed_publish)
    monkeypatch.setattr(launcher.os,'getpgid',lambda pid:pid,raising=False)
    monkeypatch.setattr(launcher.signal,'SIGKILL',9,raising=False)
    signals = []
    monkeypatch.setattr(launcher,'owned_group_alive',lambda pid:not signals or signals[-1][1]!=9)
    ticks=iter((0,121,122))
    monkeypatch.setattr(launcher.time,'monotonic',lambda:next(ticks))
    def killpg(pid,signum):
        if signum == 0:
            raise ProcessLookupError
        signals.append((pid,signum))
    monkeypatch.setattr(launcher.os,'killpg',killpg,raising=False)
    with pytest.raises(OSError,match='publication'):
        launcher.reserve_process(helper,46,'E2-R018-gate-D03',[],path,{'state':'reserved'})
    assert signals == [(123456,launcher.signal.SIGTERM),(123456,launcher.signal.SIGKILL)]
    recovery = json.loads(path.with_name(path.name+'.cleanup_123456.json').read_text())
    assert recovery['state'] == 'receipt_publish_failed_stopped'


def test_cleanup_escalates_when_leader_exits_but_child_survives(monkeypatch):
    signals=[]
    process=SimpleNamespace(pid=123456,poll=lambda:0 if signals else None)
    monkeypatch.setattr(launcher.signal,'SIGKILL',9,raising=False)
    monkeypatch.setattr(launcher.os,'getpgid',lambda pid:pid,raising=False)
    monkeypatch.setattr(launcher.os,'killpg',lambda pid,sig:signals.append(sig),raising=False)
    monkeypatch.setattr(launcher,'owned_group_alive',lambda pid:not signals or signals[-1]!=9)
    ticks=iter((0,121,122))
    monkeypatch.setattr(launcher.time,'monotonic',lambda:next(ticks))
    launcher.stop_owned_process(process)
    assert signals==[launcher.signal.SIGTERM,9]


def test_natural_exit_between_poll_and_group_lookup_succeeds(monkeypatch):
    monkeypatch.setattr(launcher.signal,'SIGKILL',9,raising=False)
    observations=iter((True,False))
    monkeypatch.setattr(launcher,'owned_group_alive',lambda pid:next(observations))
    def already_gone(pid):
        raise ProcessLookupError
    monkeypatch.setattr(launcher.os,'getpgid',already_gone,raising=False)
    monkeypatch.setattr(launcher.os,'killpg',lambda *_:pytest.fail('signal after group vanished'),raising=False)
    launcher.stop_owned_process(SimpleNamespace(pid=123456,poll=lambda:None))


@pytest.mark.skipif(os.name!='posix',reason='Linux process group lifecycle')
def test_cleanup_stops_real_term_resistant_child_after_leader_exits(tmp_path):
    import subprocess
    import sys
    import time
    child_marker=tmp_path/'child.pid'
    child_code='import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(os.getpid(),flush=True); time.sleep(30)'
    leader_code=('import subprocess,sys,time; '
        'output=open(sys.argv[1],"w"); '
        'subprocess.Popen([sys.executable,"-c",sys.argv[2]],stdout=output); time.sleep(30)')
    process=subprocess.Popen([sys.executable,'-c',leader_code,str(child_marker),child_code],start_new_session=True)
    try:
        deadline=time.monotonic()+5
        while not child_marker.is_file() or not child_marker.read_text().strip():
            assert time.monotonic()<deadline,'child did not initialize'
            time.sleep(0.01)
        launcher.stop_owned_process(process,term_timeout=0.2,kill_timeout=3)
        assert process.poll() is not None
        assert not launcher.owned_group_alive(process.pid)
    finally:
        try:
            os.killpg(process.pid,launcher.signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def test_cleanup_failure_remains_explicit(monkeypatch,tmp_path):
    path = tmp_path/'receipt.json'
    wrapper = tmp_path/'wrapper.sh'; wrapper.write_text('owned wrapper')
    helper = SimpleNamespace(reserve_and_launch=lambda *_:(SimpleNamespace(pid=123456),wrapper,tmp_path/'batch.log'))
    def failed_publish(*_):
        raise OSError('publication failed')
    def failed_stop(*_):
        raise RuntimeError('owned group still active')
    monkeypatch.setattr(launcher,'publish_receipt',failed_publish)
    monkeypatch.setattr(launcher,'stop_owned_process',failed_stop)
    with pytest.raises(RuntimeError,match='cleanup failed'):
        launcher.reserve_process(helper,46,'E2-R018-gate-D03',[],path,{'state':'reserved'})
    assert json.loads(path.with_name(path.name+'.cleanup_123456.json').read_text())['state'] == 'cleanup_failure'


@pytest.mark.skipif(os.name!='posix',reason='Linux execution directory permissions')
def test_execution_copy_rejects_writable_source_and_parent(tmp_path,monkeypatch):
    directory = tmp_path/'source'; directory.mkdir()
    runner = directory/'t16_candidate_runner.py'; runner.write_bytes(b'approved runner')
    base = directory/'t16_base_runner.py'; base.write_bytes(b'approved base')
    monkeypatch.setattr(launcher,'RUNNER_SHA',launcher.hashlib.sha256(runner.read_bytes()).hexdigest())
    monkeypatch.setattr(launcher,'BASE_SHA',launcher.hashlib.sha256(base.read_bytes()).hexdigest())
    runner.chmod(0o444); base.chmod(0o444); directory.chmod(0o555)
    launcher.verify_execution_directory(directory)
    runner.chmod(0o644)
    with pytest.raises(ValueError,match='source'):
        launcher.verify_execution_directory(directory)
    runner.chmod(0o444); directory.chmod(0o755)
    with pytest.raises(ValueError,match='directory'):
        launcher.verify_execution_directory(directory)
    directory.chmod(0o555); tmp_path.chmod(0o777)
    with pytest.raises(ValueError,match='parent'):
        launcher.verify_execution_directory(directory)
    tmp_path.chmod(0o700); directory.chmod(0o755)


@pytest.mark.skipif(os.name!='posix',reason='Linux execution directory permissions')
def test_execution_copy_remains_approved_after_mutable_stage_replacement(tmp_path,monkeypatch):
    stage = tmp_path/'stage'; stage.mkdir()
    runner = stage/'t16_candidate_runner.py'; runner.write_bytes(b'approved runner')
    base = stage/'t16_base_runner.py'; base.write_bytes(b'approved base')
    monkeypatch.setattr(launcher,'STAGE',stage)
    monkeypatch.setattr(launcher,'RUNNER_SHA',launcher.hashlib.sha256(runner.read_bytes()).hexdigest())
    monkeypatch.setattr(launcher,'BASE_SHA',launcher.hashlib.sha256(base.read_bytes()).hexdigest())
    frozen = launcher.freeze_execution_copy(tmp_path)
    runner.write_bytes(b'unapproved replacement')
    assert (frozen/runner.name).read_bytes() == b'approved runner'
    launcher.verify_execution_directory(frozen)
    frozen.chmod(0o700)


def test_declared_d07_source_and_parent_bindings():
    adapter = launcher_path.with_name('t16_candidate_runner_d07.py')
    if not adapter.is_file():
        adapter = adapter.with_name('t16_candidate_runner.py')
    source = launcher.verified_module(adapter, launcher.RUNNER_SHA, 'd07_gate_binding_check')
    assert launcher.CANDIDATES == {'D07': ('D07', 'fefb19cbac6bb1cb08835c411c895310600b3677')}
    assert source.CASES['D07']['new_commit'] == launcher.CANDIDATES['D07'][1]
    assert source.CASES['D07']['parent_commit'] == '03692633df48456fb0baa78de7b64e5628a12ab1'
    assert source.BASE_SHA256 == launcher.BASE_SHA
