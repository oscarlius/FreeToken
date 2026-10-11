"""Real POSIX signals through the candidate capture scheduler and shutdown hook."""
import ast
import contextlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time
import types

import pytest

HERE = Path(__file__).parents[1]


def _child(output, ready, cleaning, release, wrapper, second_signal_phase):
    source = Path('/data2/FreeToken/wt/e2base1-ordinary-rewind/scripts/equiv_suite/service_capture_startup.py')
    tree = ast.parse(source.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'install_scheduler_capture', 'run_scheduler'}]
    assert len(functions) == 2
    future = ast.parse('from __future__ import annotations').body[0]
    capture = types.ModuleType('equiv_suite.service_capture_startup')
    capture.__dict__.update(logging=types.SimpleNamespace(INFO=20, disable=lambda _: None), os=os,
                            ServiceCaptureError=RuntimeError, _dev_d16_destination=lambda: None)
    exec(compile(ast.Module(body=[future, *functions], type_ignores=[]), str(source), 'exec'), capture.__dict__)
    stages = []

    def checkpoint(phase):
        stages.append(phase)
        if second_signal_phase == phase:
            cleaning.set()
            deadline = time.monotonic() + 10
            while not Path(release).is_file():
                assert time.monotonic() < deadline, 'parent did not release cleanup'
                time.sleep(.01)

    class Adapter:
        def finalize(self):
            checkpoint('capture_finalize')
            Path(output + '.capture.json').write_text(json.dumps({'finalized': True, 'stages': stages}))

        def record_observer_error(self, error):
            raise AssertionError(error)

    capture.install_from_env = lambda _: Adapter()

    class Scheduler:
        gpus = []
        engine = object()

        def __init__(self, _): pass
        def sync_all_ranks(self): pass
        def _process_one_msg(self, _): pass
        def send_result(self, _): pass
        def _schedule_next_batch(self): pass

        def run_forever(self):
            ready.set()
            while True:
                time.sleep(.02)

        def shutdown(self):
            checkpoint('scheduler_shutdown')

    package = types.ModuleType('freetoken'); package.__path__ = []
    server = types.ModuleType('freetoken.server'); server.__path__ = []
    launch = types.ModuleType('freetoken.server.launch')
    launch._detach_process_group = lambda: None
    launch._report_startup_error = lambda *_: None
    server.launch = launch
    equiv = types.ModuleType('equiv_suite'); equiv.__path__ = []
    equiv.service_capture_startup = capture
    modules = {
        'equiv_suite': equiv, 'equiv_suite.service_capture_startup': capture,
        'freetoken': package, 'freetoken.server': server, 'freetoken.server.launch': launch,
        'freetoken.scheduler': types.SimpleNamespace(Scheduler=Scheduler),
        'freetoken.message': types.SimpleNamespace(UserMsg=type('UserMsg', (), {}), DetokenizeMsg=type('DetokenizeMsg', (), {})),
        'freetoken.gpu_select': types.SimpleNamespace(set_assigned_gpu=lambda _: None),
        'freetoken.utils.progress': types.SimpleNamespace(set_progress_sink=lambda _: None),
        'freetoken.kvcache.cache_status': types.SimpleNamespace(compute_cache_status_meta=lambda _: {}),
        'freetoken.utils': types.SimpleNamespace(init_logger=lambda _: types.SimpleNamespace(info=lambda *_: None)),
        'torch': types.SimpleNamespace(inference_mode=contextlib.nullcontext),
        't10_capture_startup': types.SimpleNamespace(install_terminal_cap=lambda value: value),
    }
    sys.modules.update(modules)
    spec = importlib.util.spec_from_file_location('t10_signal_wrapper', HERE / wrapper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    os.environ.update(FT_T10_WORKER_SHUTDOWN=output, FT_D16_SERVICE_CAPTURE_DIR=output + '.capture',
                      FT_D16_EXECUTION_ID='cpu-spawn', FT_DEV_ROUTE_TRACE='0', FT_DEV_PAUSE_ENDPOINT='0')
    original_fsync = os.fsync

    def fsync(fd):
        checkpoint('receipt_fsync')
        return original_fsync(fd)

    os.fsync = fsync
    args = types.SimpleNamespace(shell_mode=False, gpu_assigned=['0'], gpu=None,
                                 tp_info=types.SimpleNamespace(rank=0, size=1, is_primary=lambda: True), silent_output=False)
    module.worker_run_scheduler(args, types.SimpleNamespace(put=lambda _: None))


@pytest.mark.parametrize('phase', ['scheduler_shutdown', 'capture_finalize', 'receipt_fsync'])
@pytest.mark.parametrize('wrapper', ['t10_capture_startup_v2.py', 't10_capture_startup_v3.py'])
def test_spawn_double_sigterm_actual_capture_run_scheduler(tmp_path, wrapper, phase):
    if sys.platform != 'linux':
        pytest.skip('Linux signals and actual candidate capture source required')
    ctx = multiprocessing.get_context('spawn')
    ready, cleaning = ctx.Event(), ctx.Event()
    release = tmp_path / 'release-cleanup'
    output = tmp_path / 'worker.json'
    child = ctx.Process(target=_child, args=(str(output), ready, cleaning, str(release), wrapper, phase))
    child.start()
    try:
        assert ready.wait(15), f'child did not enter scheduler: {child.exitcode}'
        os.kill(child.pid, signal.SIGTERM)
        assert cleaning.wait(15), f'child did not reach {phase}: {child.exitcode}'
        os.kill(child.pid, signal.SIGTERM)
        release.touch()
        child.join(15)
        wanted = 0 if wrapper.endswith('v3.py') else (-signal.SIGTERM if phase == 'receipt_fsync' else 1)
        assert child.exitcode == wanted
    finally:
        if child.is_alive():
            child.kill()
            child.join(10)
    receipt = json.loads(output.read_text())
    if wrapper.endswith('v3.py'):
        assert receipt['status'] == 'complete' and receipt['pid'] == child.pid
        assert receipt['scheduler_run_started'] is True
        capture = json.loads(Path(str(output) + '.capture.json').read_text())
        assert capture == {'finalized': True, 'stages': ['scheduler_shutdown', 'capture_finalize']}
    elif phase != 'receipt_fsync':
        assert receipt['status'] == 'failed'
    # Old receipt may say complete before fsync while the process dies. Its
    # expected negative exit status above exposes that incomplete shutdown.
