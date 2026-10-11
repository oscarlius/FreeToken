"""CPU-only behavior checks; no model, GPU, real lock, or production port use."""
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

import release_config as config
import release_control as control
from test_smoke_live import (valid_projection, validate_owner, required_environment,
                            validate_health, validate_cold_rows, SmokeInvalid)


@pytest.mark.parametrize('mode', ['release', 'rollback'])
def test_environment_copy_remove_set(mode):
    parent = {'PATH': '/usr/bin', 'LD_LIBRARY_PATH': '/cuda/lib',
        'FT_DEV_TRACE': 'bad', 'FT_OTHER': 'bad', 'PYTHONPATH': 'bad',
        'CUDA_VISIBLE_DEVICES': 'bad', 'KEEP_CUSTOM': 'yes'}
    result = config.environment(mode, parent)
    assert result['LD_LIBRARY_PATH'] == '/cuda/lib' and result['KEEP_CUSTOM'] == 'yes'
    assert not any(key.startswith('FT_') for key in result)
    assert result['PYTHONPATH'] == str(config.MODES[mode][0] / 'python')
    assert result['CUDA_VISIBLE_DEVICES'] == '0' and result['MASTER_PORT'] == '8096'
    assert parent['FT_DEV_TRACE'] == 'bad'  # no caller mutation


@pytest.mark.parametrize('mode,window,chunk,layer_major', [
    ('release', '98304', '4096', True), ('rollback', '49152', '8192', False)])
def test_argv_boundaries(mode, window, chunk, layer_major):
    argv = config.serve_argv(mode)
    assert argv[argv.index('--host') + 1] == '172.16.108.9'
    assert argv[argv.index('--kv-reserve-tokens') + 1] == window
    assert argv[argv.index('--max-prefill-length') + 1] == chunk
    assert argv[argv.index('--max-running-requests') + 1] == '2'
    assert argv[argv.index('--cuda-graph-max-bs') + 1] == '2'
    assert ('--prefill-layer-major' in argv) == layer_major


def test_foreign_or_reused_pid_refused():
    actual = {'pid': 12, 'start_ticks': 200, 'execution_id': '12:200', 'pgid': 12, 'session': 12}
    d07 = SimpleNamespace(process_identity=lambda pid: actual)
    with pytest.raises(RuntimeError, match='birth/group'):
        control.verify_identity(d07, {**actual, 'start_ticks': 100})
    control.verify_identity(d07, actual)


@pytest.mark.parametrize('bad', ['', '../approve', 'a b', 'x;kill'])
def test_approval_id_is_a_safe_audit_identifier(bad):
    with pytest.raises(ValueError):
        control.approval_id(bad)


def test_existing_evidence_never_overwritten(tmp_path):
    path = tmp_path / 'owner.json'
    control.exclusive(path, {'first': True})
    with pytest.raises(FileExistsError):
        control.exclusive(path, {'other': True})
    assert json.loads(path.read_text()) == {'first': True}


@pytest.mark.parametrize('ports,gpu', [('LISTEN', ''), ('', '123')])
def test_resource_release_fails_closed(monkeypatch, ports, gpu):
    def output(argv, **kwargs):
        return ports if argv[0] == 'ss' else gpu
    monkeypatch.setattr(control.subprocess, 'check_output', output)
    ticks = iter(range(0, 200, 1))
    monkeypatch.setattr(control.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(control.time, 'sleep', lambda *_: None)
    with pytest.raises(RuntimeError, match='deadline'):
        control.resources_released(timeout=6)


def test_projection_requires_usage_and_valid_text():
    record = {'projection': {'text': 'hello', 'finish_reason': 'length',
        'usage': {'prompt_tokens': 8257, 'completion_tokens': 128, 'total_tokens': 8385}}}
    assert len(valid_projection(record, 8257)) == 64
    record['projection']['text'] = '\ufffd'
    with pytest.raises(AssertionError):
        valid_projection(record, 8257)


def test_foreground_supervisor_rejected_before_lock(monkeypatch):
    monkeypatch.setattr(control.os, 'getsid', lambda pid: os.getpid() + 1, raising=False)
    with pytest.raises(RuntimeError, match='setsid'):
        control.start('release', 'approval1', Path('/does-not-matter'))


@pytest.mark.parametrize('stop_signal', ['SIGTERM', 'SIGINT', 'SIGHUP'])
@pytest.mark.parametrize('cleanup_failure', ['none', 'resources', 'stop'])
def test_supervisor_signals_stop_owned_child_and_release(monkeypatch, tmp_path, stop_signal, cleanup_failure):
    monkeypatch.setattr(control, 'ROOT', tmp_path)
    monkeypatch.setattr(control, 'ACTIVE', tmp_path / 'production.active.json')
    monkeypatch.setattr(control, 'QUARANTINE', tmp_path / 'quarantine.json')
    monkeypatch.setattr(control, 'MODES', {'release': (tmp_path / 'wt', 'abc', 98304, 4096)})
    manifest = tmp_path / 'binary_manifest.json'
    manifest.write_text('{}')
    monkeypatch.setattr(control, 'BINARY_MANIFEST', manifest)
    monkeypatch.setattr(control, 'validate_worktree', lambda *a: {'ok': True, 'fixture': 'owned supervisor lifecycle only'})
    monkeypatch.setattr(control.os, 'getsid', lambda pid: os.getpid(), raising=False)
    monkeypatch.setattr(control.os, 'getpgrp', lambda: os.getpid(), raising=False)
    # Windows CPU fixtures can model Linux HUP without installing OS handlers.
    monkeypatch.setattr(control.signal, 'SIGHUP', 77, raising=False)
    handlers = {}
    monkeypatch.setattr(control.signal, 'getsignal', lambda sig: 'original')
    monkeypatch.setattr(control.signal, 'signal', lambda sig, fn: handlers.update({sig: fn}))
    events = []
    identity = {'pid': 123, 'start_ticks': 55, 'execution_id': '123:55', 'pgid': 123, 'session': 123}
    def stop_owned(*args):
        events.append('stop_owned')
        if cleanup_failure == 'stop':
            raise RuntimeError('simulated TERM/KILL cleanup error')
    lifecycle = SimpleNamespace(stop_owned_process=stop_owned)
    def take_lock(*args):
        assert all(callable(handlers.get(sig)) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP))
        return {'token': 'owned'}
    d07 = SimpleNamespace(load_owned_lifecycle=lambda: lifecycle,
        take_d07_gpu_lock=take_lock,
        release_d07_gpu_lock=lambda owner: events.append('release_lock'),
        require_gpu_idle=lambda: None, process_identity=lambda pid: {**identity, 'pid': pid})
    monkeypatch.setattr(control, 'helpers', lambda: d07)
    monkeypatch.setattr(control.subprocess, 'check_output', lambda argv, **kw: 'abc\n' if 'rev-parse' in argv else '')
    release_checks = []
    def resources():
        release_checks.append(1)
        events.append('resources_free')
        if len(release_checks) > 1 and cleanup_failure == 'resources':
            raise RuntimeError('simulated resource deadline')
    monkeypatch.setattr(control, 'resources_released', resources)
    class Child:
        pid = 123
        def poll(self):
            handlers[getattr(control.signal, stop_signal)](None, None)
            return None
    cwds = []
    def spawn(*args, **kwargs):
        cwds.append(kwargs['cwd'])
        return Child()
    monkeypatch.setattr(control.subprocess, 'Popen', spawn)
    parent = tmp_path / 'runs/production'
    parent.mkdir(parents=True)
    if cleanup_failure == 'none':
        control.start('release', 'approval1', parent / 'generation1')
    else:
        with pytest.raises(RuntimeError, match='quarantined'):
            control.start('release', 'approval1', parent / 'generation1')
        assert control.QUARANTINE.exists()
    assert events[-3:] == ['stop_owned', 'resources_free', 'release_lock']
    assert not control.ACTIVE.exists()
    assert (parent / 'generation1/stopped.json').is_file()
    assert all(path == parent / 'generation1' for path in cwds)
    assert all(value == 'original' for value in handlers.values())


def test_stop_waits_for_delayed_cleanup(monkeypatch, tmp_path):
    active, lock = tmp_path / 'active.json', tmp_path / 'gpu.lock'
    active.write_text(json.dumps({'supervisor': {'pid': 12, 'start_ticks': 11}, 'run_dir': str(tmp_path)}))
    lock.write_text('owned')
    monkeypatch.setattr(control, 'ACTIVE', active)
    monkeypatch.setattr(control, 'QUARANTINE', tmp_path / 'quarantine.json')
    monkeypatch.setattr(control, 'helpers', lambda: SimpleNamespace(LOCK=lock, process_identity=lambda pid: None))
    monkeypatch.setattr(control, 'verify_identity', lambda *a: None)
    monkeypatch.setattr(control.os, 'kill', lambda *a: None)
    monkeypatch.setattr(control.time, 'sleep', lambda *a: None)
    tries = []
    def free():
        tries.append(1)
        if len(tries) < 3:
            return {'ports': 'occupied', 'compute_pids': ''}
        lock.unlink()
        active.unlink()
        return {'ports': '', 'compute_pids': ''}
    monkeypatch.setattr(control, 'resource_snapshot', free)
    control.stop('stop_approval')
    assert len(tries) == 3


@pytest.mark.parametrize('mode', ['release', 'rollback'])
def test_smoke_owner_requires_exact_mode_host_argv_and_approval(mode):
    owner = {'mode': mode, 'commit': config.MODES[mode][1], 'argv': config.serve_argv(mode),
             'host': config.HOST, 'log': str(Path('/test/serve.log')), 'approval_id': 'approved1'}
    validate_owner(owner, mode, 'http://172.16.108.9:8095', Path('/test/serve.log'), 'approved1')
    with pytest.raises(AssertionError):
        validate_owner(owner, mode, 'http://127.0.0.1:12345', Path('/test/serve.log'), 'approved1')
    with pytest.raises(AssertionError):
        validate_owner(owner, mode, 'http://172.16.108.9:8095', Path('/test/serve.log'), 'foreign')


def test_explicit_smoke_missing_environment_fails():
    with pytest.raises(ValueError, match='RELEASE_SMOKE_BASE'):
        required_environment({})


@pytest.mark.parametrize('payload', [{'status': 'ok', 'maintenance': 'restarting'},
                                    {'status': 'error', 'maintenance': 'serving'}, {}])
def test_health_rejects_non_serving(payload):
    with pytest.raises(AssertionError):
        validate_health(200, payload)
    validate_health(200, {'status': 'ok', 'maintenance': 'serving'})


def test_external_prefill_is_probe_invalid():
    row = {'new_sequences': 1, 'new_tokens': 512, 'cached_tokens': 0}
    validate_cold_rows([row], 512, 4096)
    with pytest.raises(SmokeInvalid):
        validate_cold_rows([row, row], 512, 4096)
    with pytest.raises(SmokeInvalid):
        validate_cold_rows([{**row, 'new_sequences': 2}], 512, 4096)


# Prefill rows copied verbatim from DEPLOY-E2-20261009-COND-01 (481d3a7, chunk 4096) and
# ROLLBACK-E2-20261009-COND-01 (184c965, chunk 8192): both split 8257 as 512 + 7745 at the
# system-message anchor, so a ceil(prompt / chunk) row count was never a valid invariant.
_ROW = ('Prefill batch, #new-seq: 1, #new-token: {n}, #cached-token: {c}, token usage: 0.08, '
        '#mamba-slot: 3/12, mamba usage: 0.25, #running-req: 1, #queue-req: 0, '
        'input throughput (token/s): 62.34')


_ADAPTER = Path(__file__).resolve().parent.parent / 'r066b_canary_v2/sdk_adapter.py'
_PATTERN = r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)'


def _rows(*pairs):
    # Same regex the live smoke uses via r066b cached_rows(); read, not imported, because
    # the adapter imports the SDK stack. The parity assert keeps the two from drifting.
    import re
    assert _PATTERN in _ADAPTER.read_text(encoding='utf-8')
    text = '\n'.join(_ROW.format(n=n, c=c) for n, c in pairs)
    return [{'new_sequences': int(s), 'new_tokens': int(n), 'cached_tokens': int(c)}
            for s, n, c in re.findall(_PATTERN, text)]


@pytest.mark.parametrize('chunk', [4096, 8192])
def test_anchor_split_cold_rows_accepted_for_both_versions(chunk):
    validate_cold_rows(_rows((512, 0), (7745, 0)), 8257, chunk)
    validate_cold_rows(_rows((512, 0)), 512, chunk)
    validate_cold_rows(_rows((8284, 0)), 8284, chunk)  # R066b: no anchor, one whole row


def test_cold_rows_reject_cache_hit_short_total_and_empty():
    with pytest.raises(AssertionError):
        validate_cold_rows(_rows((512, 0), (7745, 64)), 8257, 4096)
    with pytest.raises(AssertionError):
        validate_cold_rows(_rows((512, 0), (7700, 0)), 8257, 4096)
    with pytest.raises(AssertionError):
        validate_cold_rows([], 8257, 4096)


def test_cold_rows_overflow_is_probe_invalid_not_rollback():
    with pytest.raises(SmokeInvalid):
        validate_cold_rows(_rows((512, 0), (7745, 0), (512, 0)), 8257, 4096)


@pytest.mark.parametrize('output,xml,code', [
    ('1 skipped', '<testsuite tests="1" skipped="1"/>', 0),
    ('1 passed', '<testsuite tests="2" skipped="1"/>', 0),
    ('2 passed', '<testsuite tests="1"/>', 0),
    ('1 passed', '<testsuite tests="1"/>', 1)])
def test_smoke_gate_rejects_skip_count_or_exit(output, xml, code):
    from run_smoke import check_result
    with pytest.raises(RuntimeError):
        check_result(output, xml, code)
    assert check_result('1 passed in 1.0s', '<testsuite tests="1" skipped="0"/>', 0)['passed'] == 1


def test_resource_release_retries_transient_occupancy(monkeypatch):
    snapshots = iter([{'ports': '8095', 'compute_pids': ''},
                      {'ports': '', 'compute_pids': '12'}, {'ports': '', 'compute_pids': ''}])
    monkeypatch.setattr(control, 'resource_snapshot', lambda *a: next(snapshots))
    monkeypatch.setattr(control.time, 'sleep', lambda *a: None)
    assert control.resources_released(60) == {'ports': '', 'compute_pids': ''}
    with pytest.raises(ValueError):
        control.resources_released(61)


def _run_monitor(tmp_path, healthy_sequence, exit_after, approved_stop=False, crash_stopped=False):
    from monitor_health import monitor
    born = {'pid': 12, 'start_ticks': 1, 'pgid': 12, 'session': 12}
    now = [0.0]
    checks = []
    def sleep(seconds):
        now[0] += seconds
    def check():
        checks.append(now[0])
        return {'healthy': healthy_sequence(len(checks) - 1)}
    def identity(pid):
        if now[0] < exit_after:
            return born
        # Files appear only at exit time, as in release_control: stop() writes
        # stop_<approval>.json before SIGTERM; the supervisor finally writes stopped.json.
        if approved_stop:
            (tmp_path / 'stop_STOP-TEST.json').write_text('{}')
        if approved_stop or crash_stopped:
            (tmp_path / 'stopped.json').write_text('{}')
        return None
    monitor(tmp_path, born, identity, check=check, sleep=sleep, clock=lambda: now[0])
    path = tmp_path / 'alerts.jsonl'
    return checks, [json.loads(line)['event'] for line in path.read_text().splitlines()] if path.exists() else []


def test_monitor_three_failures_after_serving_and_supervisor_exit(tmp_path):
    checks, events = _run_monitor(tmp_path, lambda i: i == 0, 181)
    assert checks == [0, 60, 120, 180]
    assert events == ['three_consecutive_health_failures', 'supervisor_exit']


def test_monitor_cold_start_loading_is_not_a_failure(tmp_path):
    # DEPLOY-E2-20261009-COND-01 alerted while expert banks were still loading.
    checks, events = _run_monitor(tmp_path, lambda i: i >= 5, 600)
    assert len(checks) == 10 and events == ['supervisor_exit']


def test_monitor_startup_timeout_alerts_once(tmp_path):
    checks, events = _run_monitor(tmp_path, lambda i: False, 1900)
    assert events == ['startup_not_serving', 'supervisor_exit']


def test_monitor_quiet_after_approved_stop(tmp_path):
    checks, events = _run_monitor(tmp_path, lambda i: True, 61, approved_stop=True)
    assert events == []


def test_monitor_alerts_on_crash_even_if_stopped_json_written(tmp_path):
    checks, events = _run_monitor(tmp_path, lambda i: True, 61, crash_stopped=True)
    assert events == ['supervisor_exit']


def test_cold_rows_zero_sequence_row_is_probe_invalid():
    with pytest.raises(SmokeInvalid):
        validate_cold_rows([{'new_sequences': 0, 'new_tokens': 512, 'cached_tokens': 0}], 512, 4096)


def _baseline(rows, sha='a' * 64):
    return {'long': {'backend_cache_rows': rows, 'sha256': sha,
                     'usage': {'prompt_tokens': 8257, 'completion_tokens': 128, 'total_tokens': 8385}}}


def test_baseline_compares_row_structure_then_sha():
    from test_smoke_live import compare_with_baseline
    split = _rows((512, 0), (7745, 0))
    compare_with_baseline(_baseline(split), _baseline(split))
    with pytest.raises(AssertionError):
        compare_with_baseline(_baseline(_rows((8257, 0))), _baseline(split))
    with pytest.raises(AssertionError):
        compare_with_baseline(_baseline(split, 'b' * 64), _baseline(split))
    legacy = _baseline(split)
    del legacy['long']['backend_cache_rows']
    with pytest.raises(AssertionError):
        compare_with_baseline(_baseline(split), legacy)


def test_explicit_pytest_smoke_no_variables_cannot_skip(tmp_path):
    import subprocess
    import sys
    env = {key: value for key, value in os.environ.items() if not key.startswith('RELEASE_SMOKE_')}
    env.update(CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        str(Path(__file__).with_name('test_smoke_live.py'))], cwd=tmp_path, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert result.returncode != 0 and '1 failed' in result.stdout
    assert 'skipped' not in result.stdout and 'Explicit smoke requires variables' in result.stdout


def test_environment_diff_never_exports_host_credentials():
    projection = config.environment_projection({'PATH': '/usr/bin', 'PYTHONPATH': '/old',
        'FT_DEV_D0_PATH': '/trace', 'FT_SSH_PASSWORD': 'never-export',
        'HF_TOKEN': 'never-export', 'AWS_SECRET_ACCESS_KEY': 'never-export'})
    assert projection == {'FT_DEV_D0_PATH': '/trace', 'PATH': '/usr/bin', 'PYTHONPATH': '/old'}


def test_start_rejects_worktree_before_run_directory_or_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(control.os, 'getsid', lambda pid: os.getpid(), raising=False)
    monkeypatch.setattr(control.os, 'getpgrp', lambda: os.getpid(), raising=False)
    monkeypatch.setattr(control, 'ROOT', tmp_path)
    monkeypatch.setattr(control, 'ACTIVE', tmp_path / 'active.json')
    monkeypatch.setattr(control, 'QUARANTINE', tmp_path / 'quarantine.json')
    worktree = tmp_path / 'wt'
    monkeypatch.setattr(control, 'MODES', {'release': (worktree, 'abc', 98304, 4096)})
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    monkeypatch.setattr(control, 'BINARY_MANIFEST', manifest)
    locks = []
    monkeypatch.setattr(control, 'helpers', lambda: SimpleNamespace(take_d07_gpu_lock=lambda *a: locks.append(a)))
    def reject(path, commit, packet, mode):
        assert (path, commit, packet, mode) == (worktree, 'abc', {}, 'release')
        raise RuntimeError('unapproved ignored file')
    monkeypatch.setattr(control, 'validate_worktree', reject)
    run = tmp_path / 'runs/production/new-generation'
    with pytest.raises(RuntimeError, match='unapproved ignored'):
        control.start('release', 'approval1', run)
    assert not run.exists() and locks == []
