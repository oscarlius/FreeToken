"""CPU-only behavior checks; no model, GPU, real lock, or production port use."""
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

import release_config as config
import release_control as control
from test_smoke_live import valid_projection, validate_owner


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
    with pytest.raises(RuntimeError, match='preserve owner lock'):
        control.resources_released()


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
def test_supervisor_signals_stop_owned_child_and_release(monkeypatch, tmp_path, stop_signal):
    monkeypatch.setattr(control, 'ROOT', tmp_path)
    monkeypatch.setattr(control, 'ACTIVE', tmp_path / 'production.active.json')
    monkeypatch.setattr(control, 'MODES', {'release': (tmp_path / 'wt', 'abc', 98304, 4096)})
    monkeypatch.setattr(control.os, 'getsid', lambda pid: os.getpid(), raising=False)
    monkeypatch.setattr(control.os, 'getpgrp', lambda: os.getpid(), raising=False)
    # Windows CPU fixtures can model Linux HUP without installing OS handlers.
    monkeypatch.setattr(control.signal, 'SIGHUP', 77, raising=False)
    handlers = {}
    monkeypatch.setattr(control.signal, 'getsignal', lambda sig: 'original')
    monkeypatch.setattr(control.signal, 'signal', lambda sig, fn: handlers.update({sig: fn}))
    events = []
    identity = {'pid': 123, 'start_ticks': 55, 'execution_id': '123:55', 'pgid': 123, 'session': 123}
    lifecycle = SimpleNamespace(stop_owned_process=lambda *a: events.append('stop_owned'))
    d07 = SimpleNamespace(load_owned_lifecycle=lambda: lifecycle,
        take_d07_gpu_lock=lambda *a: {'token': 'owned'},
        release_d07_gpu_lock=lambda owner: events.append('release_lock'),
        require_gpu_idle=lambda: None, process_identity=lambda pid: {**identity, 'pid': pid})
    monkeypatch.setattr(control, 'helpers', lambda: d07)
    monkeypatch.setattr(control.subprocess, 'check_output', lambda argv, **kw: 'abc\n' if 'rev-parse' in argv else '')
    monkeypatch.setattr(control, 'resources_released', lambda: events.append('resources_free'))
    class Child:
        pid = 123
        def poll(self):
            handlers[getattr(control.signal, stop_signal)](None, None)
            return None
    monkeypatch.setattr(control.subprocess, 'Popen', lambda *a, **kw: Child())
    parent = tmp_path / 'runs/production'
    parent.mkdir(parents=True)
    control.start('release', 'approval1', parent / 'generation1')
    assert events[-3:] == ['stop_owned', 'resources_free', 'release_lock']
    assert not control.ACTIVE.exists()
    assert (parent / 'generation1/stopped.json').is_file()


def test_stop_waits_for_delayed_cleanup(monkeypatch, tmp_path):
    active, lock = tmp_path / 'active.json', tmp_path / 'gpu.lock'
    active.write_text(json.dumps({'supervisor': {'pid': 12, 'start_ticks': 11}, 'run_dir': str(tmp_path)}))
    lock.write_text('owned')
    monkeypatch.setattr(control, 'ACTIVE', active)
    monkeypatch.setattr(control, 'helpers', lambda: SimpleNamespace(LOCK=lock, process_identity=lambda pid: None))
    monkeypatch.setattr(control, 'verify_identity', lambda *a: None)
    monkeypatch.setattr(control.os, 'kill', lambda *a: None)
    monkeypatch.setattr(control.time, 'sleep', lambda *a: None)
    tries = []
    def free():
        tries.append(1)
        if len(tries) < 3:
            raise RuntimeError('cleanup in progress')
        lock.unlink()
        active.unlink()
    monkeypatch.setattr(control, 'resources_released', free)
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
