import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

import pytest


PATH = Path(__file__).resolve().parents[1] / 'd06_gpu_selfcheck.py'
spec = importlib.util.spec_from_file_location('d06_gpu_selfcheck_under_test', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def g3_fixture(tmp_path, tps=31.7):
    rows = []
    for uid in range(2):
        sidecar = tmp_path / f'way{uid}.json'
        events = [{'uid': uid, 'request_seq': number, 'completion_tokens_delta': 1,
                   'completion_tokens_cumulative': number, 't_s': number / tps}
                  for number in range(1, 513)]
        sidecar.write_text(json.dumps({'uid': uid, 'token_events': events}))
        rows.append({'uid': uid, 'decode_tps': tps, 'completion_tokens': 512,
                     't_first': events[0]['t_s'], 't_last': events[-1]['t_s'],
                     'token_timestamps': str(sidecar)})
    return {'schema': 'multisession_probe/v1', 'command': 'two-decode', 'same_prompt': True,
            'reps': [{'per_way': rows, 'frontend_token_counts': [32000, 32000],
                      'prompt_sha256': ['same', 'same']}]}


def h1_fixture(tmp_path, start, end):
    base = tmp_path / 'd0'
    base.with_name(base.name + '_decode_steps.jsonl').write_text(json.dumps({'step': 1, 't': start - 1}) + '\n')
    base.with_name(base.name + '_decode_timeline.jsonl').write_text(json.dumps({'step': 1, 't': start - 1}) + '\n')
    base.with_name(base.name + '_prefill.jsonl').write_text(json.dumps({'t_start': start - 2, 't_end': start - 1}) + '\n')
    return {'schema': 'multisession_probe/v1', 'command': 'h1', 'reps': [
        {'idle': {
            'event': {'event_start_wallclock_s': start, 'event_end_wallclock_s': end,
                      'pause': {'response': {'pause_started_wallclock_s': start, 'deadline_wallclock_s': end}}},
            'evidence': {'d0_base': str(base), 'event_counters': {'steps': []}},
        }}]}


def test_g3_requires_actual_two_way_ack_sidecars_and_fixed_range(tmp_path):
    assert module.validate_g3(g3_fixture(tmp_path))['bounds'] == [25.36, 38.04]
    with pytest.raises(ValueError, match='outside'):
        module.validate_g3(g3_fixture(tmp_path, 38.041))
    bad = g3_fixture(tmp_path, 31.7)
    bad['reps'][0]['per_way'][0]['completion_tokens'] = 511
    with pytest.raises(ValueError, match='length'):
        module.validate_g3(bad)
    bad = g3_fixture(tmp_path, 31.7)
    json_path = Path(bad['reps'][0]['per_way'][0]['token_timestamps'])
    evidence = json.loads(json_path.read_text())
    evidence['token_events'][3]['request_seq'] = 99
    json_path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match='sequence'):
        module.validate_g3(bad)
    bad = g3_fixture(tmp_path, 31.7)
    bad['reps'][0]['per_way'][1] = dict(bad['reps'][0]['per_way'][0])
    with pytest.raises(ValueError, match='distinct request UIDs'):
        module.validate_g3(bad)


def test_g4_rejects_batch_overlap_or_missing_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    log = tmp_path / 'serve.log'
    log.write_text('[2026-10-04|12:00:00|core] Prefill batch\n')
    start = module.dt.datetime(2026, 10, 4, 12, 0, 1).timestamp()
    end = module.dt.datetime(2026, 10, 4, 12, 0, 2).timestamp()
    assert module.validate_g4(h1_fixture(tmp_path, start, end), log)['batch_lines_checked'] == 1
    with pytest.raises(ValueError, match='contains scheduler'):
        module.validate_g4(h1_fixture(tmp_path, start - 2, end), log)
    log.write_text('[2026-10-04|12:00:01|core] Decode batch\n')
    assert module.validate_g4(h1_fixture(tmp_path, start + .9, end + .1), log)['batch_lines_checked'] == 1
    log.write_text('Prefill batch\n')
    with pytest.raises(ValueError, match='lacks wall-clock'):
        module.validate_g4(h1_fixture(tmp_path, start, end), log)


def test_g4_rejects_exact_d0_work_inside_the_idle_window(tmp_path, monkeypatch):
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    start = module.dt.datetime(2026, 10, 4, 12, 0, 1).timestamp()
    end = start + 1
    h1 = h1_fixture(tmp_path, start, end)
    base = Path(h1['reps'][0]['idle']['evidence']['d0_base'])
    base.with_name(base.name + '_decode_steps.jsonl').write_text(json.dumps({'step': 2, 't': start + .5}) + '\n')
    base.with_name(base.name + '_decode_timeline.jsonl').write_text(json.dumps({'step': 2, 't': start + .5}) + '\n')
    log = tmp_path / 'serve.log'
    log.write_text('')
    with pytest.raises(ValueError, match='exact D0 evidence'):
        module.validate_g4(h1, log)


def test_environment_is_explicit_and_clears_unrelated_dev_flags(monkeypatch, tmp_path):
    monkeypatch.setenv('FT_DEV_ROUTE_TRACE', '1')
    monkeypatch.setenv('FT_D3_DUMP', '1')
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '')
    env = module.environment(tmp_path / 'arm')
    assert env['CUDA_VISIBLE_DEVICES'] == '0'
    assert env['FT_DEV_PAUSE_ENDPOINT'] == '1'
    assert env['FT_DEV_D0_TIMELINE_STEPS'] == '20000'
    assert 'FT_DEV_ROUTE_TRACE' not in env and 'FT_D3_DUMP' not in env


def test_default_cli_refuses_run_on_cpu_host():
    with pytest.raises(SystemExit):
        module.main([])


def test_run_signal_enters_owned_cleanup_and_restores_handlers(monkeypatch):
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    handlers = {module.signal.SIGINT: 'previous-int', module.signal.SIGTERM: 'previous-term'}
    def register(signum, handler):
        previous = handlers[signum]
        handlers[signum] = handler
        return previous
    monkeypatch.setattr(module.signal, 'signal', register)
    cleaned = []
    def cleanup(*_):
        assert handlers[module.signal.SIGTERM] == module.signal.SIG_IGN
        assert handlers[module.signal.SIGINT] == module.signal.SIG_IGN
        cleaned.append(True)
    monkeypatch.setattr(module, '_stop', cleanup)
    def controlled_run():
        try:
            handlers[module.signal.SIGTERM](module.signal.SIGTERM, None)
        finally:
            # Repeated termination is deferred even before stop enters its wait.
            handlers[module.signal.SIGTERM](module.signal.SIGTERM, None)
            module.stop(None, {})
    monkeypatch.setattr(module, 'run', controlled_run)
    with pytest.raises(InterruptedError, match='signal'):
        module.main(['--run'])
    assert cleaned == [True]
    assert handlers == {module.signal.SIGINT:'previous-int', module.signal.SIGTERM:'previous-term'}


def test_builtin_selftest_needs_no_gpu(capsys):
    module.self_test()
    assert 'SELFTEST PASS' in capsys.readouterr().out


def test_stop_failure_is_lock_retaining(monkeypatch):
    module.CLEANUP_FAILED = False
    monkeypatch.setattr(module.os, 'getpgid', lambda _: 55, raising=False)
    monkeypatch.setattr(module.os, 'getsid', lambda _: 55, raising=False)
    monkeypatch.setattr(module, 'verified_group_members', lambda *_: {55})
    monkeypatch.setattr(module.os, 'killpg', lambda *_: None, raising=False)
    monkeypatch.setattr(module, 'STOP_STEPS', ((module.signal.SIGINT, 0),))
    proc = type('Proc', (), {'pid': 55, 'wait': lambda *_: None})()
    with pytest.raises(RuntimeError, match='survived'):
        module.stop(proc, {'pid': 55})
    assert module.CLEANUP_FAILED is True


@pytest.mark.skipif(os.name != 'posix', reason='requires Linux process groups')
def test_stop_kills_a_real_owned_child_group(monkeypatch):
    child = subprocess.Popen(['sleep', '30'], start_new_session=True)
    monkeypatch.setattr(module, 'STOP_STEPS', ((module.signal.SIGINT, 2),))
    monkeypatch.setattr(module, 'output', lambda _argv, **_kwargs: '0')

    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def connect_ex(self, _): return 1
    monkeypatch.setattr(module.socket, 'socket', Socket)
    try:
        module.stop(child, module.process_birth(child.pid))
        assert child.poll() is not None
        assert not module.owned_group_members(child.pid)
    finally:
        try:
            os.killpg(child.pid, module.signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


@pytest.mark.skipif(os.name != 'posix', reason='requires Linux process groups')
def test_stop_cleans_child_after_leader_exits(monkeypatch, tmp_path):
    marker = tmp_path / 'exit'
    script = ('import pathlib,subprocess,time,sys; subprocess.Popen(["sleep","30"]); '
              'marker=pathlib.Path(sys.argv[1]); '
              'exec("while not marker.exists(): time.sleep(.01)")')
    leader = subprocess.Popen([module.sys.executable, '-c', script, str(marker)], start_new_session=True)
    birth = module.process_birth(leader.pid)
    monkeypatch.setattr(module, 'STOP_STEPS', ((module.signal.SIGTERM, 2), (module.signal.SIGKILL, 2)))
    monkeypatch.setattr(module, 'output', lambda _argv, **_kwargs: '0')
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def connect_ex(self, _): return 1
    monkeypatch.setattr(module.socket, 'socket', Socket)
    try:
        deadline = time.monotonic() + 5
        while len(module.owned_group_members(leader.pid)) < 2:
            assert time.monotonic() < deadline
            time.sleep(.01)
        marker.touch()
        leader.wait(timeout=5)
        assert module.owned_group_members(leader.pid)
        module.stop(leader, birth)
        assert not module.owned_group_members(leader.pid)
        assert module.CLEANUP_FAILED is False
    finally:
        try:
            os.killpg(leader.pid, module.signal.SIGKILL)
        except ProcessLookupError:
            pass
        leader.wait(timeout=5)


def test_run_finalizes_log_before_g4_and_pass_publication(monkeypatch, tmp_path):
    root = tmp_path / 'run'
    lock = tmp_path / 'gpu.lock'
    order = []
    monkeypatch.setattr(module, 'OUT', root)
    monkeypatch.setattr(module, 'LOCK', lock)
    monkeypatch.setattr(module, 'gate', lambda: {'candidate_probe_sha256':'fixture'})
    monkeypatch.setattr(module.os, 'getpgid', lambda _: 55, raising=False)
    monkeypatch.setattr(module.os, 'getsid', lambda _: 55, raising=False)
    monkeypatch.setattr(module, 'process_birth', lambda _: {'pid':55})
    class Proc:
        pid = 55
        def poll(self): return None
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *_, **__: Proc())
    class Health:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b'{"status":"ok"}'
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *_, **__: Health())
    def probe(argv, **kwargs):
        Path(argv[argv.index('--out')+1]).write_text('{}')
    monkeypatch.setattr(module.subprocess, 'run', probe)
    monkeypatch.setattr(module, 'validate_g3', lambda _: {'fixture':True})
    def cleanup(*_):
        order.append('stop')
        with (root/'candidate/serve.log').open('a') as stream:
            stream.write('[2026-10-04|12:00:01|core] Decode batch\n')
        module.CLEANUP_FAILED = False
    monkeypatch.setattr(module, 'stop', cleanup)
    def final_check(_data, log):
        order.append('validate')
        assert order == ['stop','validate']
        assert 'Decode batch' in log.read_text()
        raise ValueError('post-stop batch violates the idle interval')
    monkeypatch.setattr(module, 'validate_g4', final_check)
    with pytest.raises(ValueError, match='post-stop batch'):
        module.run()
    assert not (root/'result.json').exists()
    assert (root/'error.json').exists()
    assert not lock.exists()
