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


def _original_worker_fixture(output, ready):
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
    module = load('r052_shutdown_fixture', HERE / 'r052_d0_shutdown_startup_v1.py')
    os.environ['FT_DEV_D0'] = '1'
    os.environ['FT_R052_WORKER_SHUTDOWN'] = str(Path(output).with_suffix('.worker.json'))
    args = types.SimpleNamespace(shell_mode=False, gpu_assigned=['0'], gpu=None,
                                 tp_info=types.SimpleNamespace(rank=0, size=1, is_primary=lambda: True),
                                 silent_output=False)
    module.worker_run_scheduler(args, types.SimpleNamespace(put=lambda _: None))


def test_spawn_sigterm_uses_actual_original_scheduler_shutdown(tmp_path):
    if sys.platform != 'linux':
        pytest.skip('actual Linux SIGTERM and candidate path required')
    ctx = multiprocessing.get_context('spawn')
    ready = ctx.Event()
    output = tmp_path / 'shutdown.json'
    child = ctx.Process(target=_original_worker_fixture, args=(str(output), ready))
    child.start()
    try:
        assert ready.wait(15)
        os.kill(child.pid, signal.SIGTERM)
        child.join(15)
        assert child.exitcode == 0
    finally:
        if child.is_alive(): child.kill(); child.join(10)
    assert json.loads(output.read_text()) == {'shutdown_calls': 1}
    receipt = json.loads(output.with_suffix('.worker.json').read_text())
    assert receipt['status'] == 'complete' and receipt['pid'] == child.pid
    assert receipt['scheduler_run_started'] is True


def test_new_service_command_uses_shutdown_wrapper_and_writable_runtime(tmp_path):
    tools = load('r052_replay_runtime_test', HERE / 'r052_t11_replay.py')
    gate = load('r052_gate_runtime_test', HERE / 'd07_g3g4_prepare.py')
    port, pair = tools.private_port_pair()
    _, argv, probes = tools.prepare_service_files(gate, tmp_path, Path('candidate'), port, file_dry_run=True)
    assert pair['tcpstore'] == port + 1
    assert 'r052_d0_shutdown_startup_v1.py' in ' '.join(argv)
    assert argv[argv.index('--kv-reserve-tokens') + 1] == '98304'
    runtime = tmp_path / 'runtime/r052_d0_shutdown_startup_v1.py'
    assert runtime.read_bytes() == (HERE / 'r052_d0_shutdown_startup_v1.py').read_bytes()
    assert runtime.stat().st_mode & 0o200
    assert any(row['path'].endswith('worker_shutdown.json') for row in probes)
