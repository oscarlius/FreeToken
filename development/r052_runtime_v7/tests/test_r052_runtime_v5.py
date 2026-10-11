"""R052 real port allocation and original-worker shutdown regression checks."""
import ast
import contextlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import sys
import time
import types

import pytest

HERE = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pair_allocator_avoids_an_occupied_tcpstore(monkeypatch):
    module = load('r052_ports_test', HERE / 'ft_batch_port_pair_v1.py')
    with socket.socket() as busy:
        busy.bind(('0.0.0.0', 0))
        blocked = busy.getsockname()[1] - 1
        with pytest.raises(OSError):
            module.probe_pair(blocked)
        port = module.dynamic_port()
        receipt = module.port_receipt(port)
    assert receipt['api'] == port and receipt['tcpstore'] == port + 1
    assert not {port, port + 1} & {8095, 8099}
    assert receipt['reservation_held_at_service_start'] is False


def _original_worker_fixture(output, ready, cleanup_ready, cleanup_release, wrapper_name):
    """Exercise the actual candidate _run_scheduler AST with CPU stand-ins."""
    candidate = Path('/data2/FreeToken/wt/e2base1-ordinary-rewind')
    source = candidate / 'python/freetoken/server/launch.py'
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == '_run_scheduler')
    function.returns = None
    for argument in function.args.args:
        argument.annotation = None
    launch = types.ModuleType('freetoken.server.launch')
    launch.__dict__.update(logging=types.SimpleNamespace(INFO=20, disable=lambda _: None),
                           _report_startup_error=lambda *_: None, init_logger=lambda _: types.SimpleNamespace(info=lambda *_: None))
    launch._detach_process_group = lambda: None
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), launch.__dict__)

    class Scheduler:
        calls = 0
        gpus = []
        engine = object()
        def __init__(self, _): pass
        def sync_all_ranks(self): pass
        def run_forever(self):
            ready.set()
            while True: time.sleep(0.02)
        def shutdown(self):
            self.calls += 1
            cleanup_ready.set()
            cleanup_release.wait(10)
            Path(output).write_text(json.dumps({'shutdown_calls': self.calls}))

    modules = {
        'freetoken': types.ModuleType('freetoken'),
        'freetoken.server': types.ModuleType('freetoken.server'),
        'freetoken.server.launch': launch,
        'freetoken.scheduler': types.SimpleNamespace(Scheduler=Scheduler),
        'freetoken.gpu_select': types.SimpleNamespace(set_assigned_gpu=lambda _: None),
        'freetoken.utils.progress': types.SimpleNamespace(set_progress_sink=lambda _: None),
        'freetoken.kvcache.cache_status': types.SimpleNamespace(compute_cache_status_meta=lambda _: {}),
        'freetoken.utils': types.SimpleNamespace(init_logger=lambda _: types.SimpleNamespace(info=lambda *_: None)),
        'torch': types.SimpleNamespace(inference_mode=contextlib.nullcontext),
    }
    sys.modules.update(modules)
    modules['freetoken.server'].launch = launch
    module = load('r052_shutdown_fixture', HERE / wrapper_name)
    os.environ['FT_DEV_D0'] = '1'
    os.environ['FT_R052_WORKER_SHUTDOWN'] = str(Path(output).with_suffix('.worker.json'))
    args = types.SimpleNamespace(shell_mode=False, gpu_assigned=['0'], gpu=None,
                                 tp_info=types.SimpleNamespace(rank=0, size=1, is_primary=lambda: True),
                                 silent_output=False)
    module.worker_run_scheduler(args, types.SimpleNamespace(put=lambda _: None))


@pytest.mark.parametrize('wrapper_name, expected_status', [
    ('r052_d0_shutdown_startup_v1.py', 'failed'),
    ('r052_d0_shutdown_startup_v2.py', 'complete'),
])
def test_spawn_double_sigterm_uses_actual_original_scheduler_shutdown(tmp_path, wrapper_name, expected_status):
    if sys.platform != 'linux':
        pytest.skip('actual Linux SIGTERM and candidate path required')
    ctx = multiprocessing.get_context('spawn')
    ready = ctx.Event()
    cleanup_ready = ctx.Event()
    cleanup_release = ctx.Event()
    output = tmp_path / 'shutdown.json'
    child = ctx.Process(target=_original_worker_fixture,
                        args=(str(output), ready, cleanup_ready, cleanup_release, wrapper_name))
    child.start()
    try:
        assert ready.wait(15)
        os.kill(child.pid, signal.SIGTERM)
        assert cleanup_ready.wait(15)
        os.kill(child.pid, signal.SIGTERM)
        cleanup_release.set()
        child.join(15)
        assert child.exitcode == (0 if expected_status == 'complete' else 1)
    finally:
        if child.is_alive(): child.kill(); child.join(10)
    if expected_status == 'complete':
        assert json.loads(output.read_text()) == {'shutdown_calls': 1}
    receipt = json.loads(output.with_suffix('.worker.json').read_text())
    assert receipt['status'] == expected_status and receipt['pid'] == child.pid
    assert receipt['scheduler_run_started'] is True


def test_new_service_command_uses_shutdown_wrapper_and_writable_runtime(tmp_path):
    tools = load('r052_replay_runtime_test', HERE / 'r052_t11_replay.py')
    gate = load('r052_gate_runtime_test', HERE / 'd07_g3g4_prepare.py')
    port, pair = tools.private_port_pair()
    _, argv, probes = tools.prepare_service_files(gate, tmp_path, Path('candidate'), port, file_dry_run=True)
    assert pair['tcpstore'] == port + 1
    assert 'r052_d0_shutdown_startup_v2.py' in ' '.join(argv)
    assert argv[argv.index('--kv-reserve-tokens') + 1] == '98304'
    runtime = tmp_path / 'runtime/r052_d0_shutdown_startup_v2.py'
    assert runtime.read_bytes() == (HERE / 'r052_d0_shutdown_startup_v2.py').read_bytes()
    assert runtime.stat().st_mode & 0o200
    assert any(row['path'].endswith('worker_shutdown.json') for row in probes)


def test_actual_shutdown_wrapper_receives_serve_without_duplicate_ft(monkeypatch, tmp_path):
    tools = load('r052_replay_wrapper_contract', HERE / 'r052_t11_replay.py')
    wrapper = load('r052_shutdown_wrapper_contract', HERE / 'r052_d0_shutdown_startup_v2.py')
    gate = types.SimpleNamespace(
        VENV=Path('/data2/FreeToken/venv'),
        clean_environment=lambda _: {'PYTHONPATH': 'candidate/python', 'VIRTUAL_ENV': 'venv', 'CUDA_VISIBLE_DEVICES': ''},
        serve_argv=lambda port: ['ft', 'serve', '--port', str(port), '--prefill-layer-major',
                                 '--mamba-host-slots', '0', '--kv-reserve-tokens', '49152',
                                 '--max-seq-len-override', '49152'],
        write_new=lambda path, value: path.write_text(json.dumps(value)))
    _, argv, _ = tools.prepare_service_files(gate, tmp_path, Path('candidate'), 45678, file_dry_run=True)
    wrapper_at = argv.index(str(tmp_path / 'runtime' / 'r052_d0_shutdown_startup_v2.py'))
    package = types.ModuleType('freetoken'); package.__path__ = []
    server = types.ModuleType('freetoken.server')
    launch = types.ModuleType('freetoken.server.launch'); launch._run_scheduler = lambda *_: None
    server.launch = launch
    cli = types.ModuleType('freetoken.cli'); seen = []
    def fake_ft_main():
        seen.append(sys.argv[:])
        if sys.argv[1] != 'serve':
            raise RuntimeError('unknown ft command: ' + sys.argv[1])
    cli.main = fake_ft_main
    monkeypatch.setitem(sys.modules, 'freetoken', package)
    monkeypatch.setitem(sys.modules, 'freetoken.server', server)
    monkeypatch.setitem(sys.modules, 'freetoken.server.launch', launch)
    monkeypatch.setitem(sys.modules, 'freetoken.cli', cli)
    original = sys.argv[:]
    try:
        assert wrapper.main(argv[wrapper_at + 1:]) is None
        assert seen == [['ft', 'serve', '--port', '45678', '--mamba-host-slots', '32',
                         '--kv-reserve-tokens', '98304', '--max-seq-len-override', '98304']]
        with pytest.raises(RuntimeError, match='unknown ft command'):
            wrapper.main([str(gate.VENV / 'bin/ft'), 'serve'])
    finally:
        sys.argv[:] = original


def _double_signal_worker(module, monkeypatch, tmp_path):
    tmp_path.mkdir()
    handlers = {}

    class Scheduler:
        def __init__(self, *_): pass
        def run_forever(self):
            handlers['handler'](signal.SIGTERM, None)
        def shutdown(self):
            handlers['handler'](signal.SIGTERM, None)

    def original(args, ack_queue):
        scheduler = Scheduler()
        try:
            scheduler.run_forever()
        except KeyboardInterrupt:
            scheduler.shutdown()
        return 'graceful-complete'

    package = types.ModuleType('freetoken'); package.__path__ = []
    server = types.ModuleType('freetoken.server')
    launch = types.ModuleType('freetoken.server.launch'); launch._run_scheduler = original
    server.launch = launch
    monkeypatch.setitem(sys.modules, 'freetoken', package)
    monkeypatch.setitem(sys.modules, 'freetoken.server', server)
    monkeypatch.setitem(sys.modules, 'freetoken.server.launch', launch)
    monkeypatch.setitem(sys.modules, 'freetoken.scheduler', types.SimpleNamespace(Scheduler=Scheduler))
    monkeypatch.setattr(module.signal, 'getsignal', lambda _: 'previous-handler')
    monkeypatch.setattr(module.signal, 'signal', lambda _, handler: handlers.__setitem__('handler', handler))
    output = tmp_path / 'worker_shutdown.json'
    monkeypatch.setenv('FT_DEV_D0', '1')
    monkeypatch.setenv('FT_R052_WORKER_SHUTDOWN', str(output))
    return module.worker_run_scheduler(types.SimpleNamespace(), types.SimpleNamespace()), output, handlers


def test_double_sigterm_during_actual_shutdown_is_failed_in_v1_and_complete_in_v2(monkeypatch, tmp_path):
    old = load('r052_shutdown_v1', HERE / 'r052_d0_shutdown_startup_v1.py')
    with pytest.raises(KeyboardInterrupt):
        _double_signal_worker(old, monkeypatch, tmp_path / 'old')
    old_receipt = json.loads((tmp_path / 'old' / 'worker_shutdown.json').read_text())
    assert old_receipt['status'] == 'failed'

    new = load('r052_shutdown_v2', HERE / 'r052_d0_shutdown_startup_v2.py')
    result, output, handlers = _double_signal_worker(new, monkeypatch, tmp_path / 'new')
    assert result == 'graceful-complete'
    new_receipt = json.loads((tmp_path / 'new' / 'worker_shutdown.json').read_text())
    assert new_receipt['status'] == 'complete'
    assert new_receipt['scheduler_run_started'] is True
    assert handlers['handler'] == 'previous-handler'
