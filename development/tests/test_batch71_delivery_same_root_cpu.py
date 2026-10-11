"""CPU-only comparison of real scheduler dispatch and the frozen stop boundary.

No model, ports or GPU: the worker is a bounded stand-in after message delivery.
SIGTERM and the original launcher try/except are real, not mocked signals.
"""
import ast
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
import types

import pytest

BASE = Path('/data2/FreeToken/wt/e2base1-ordinary-rewind')
PATCH = Path('/data2/FreeToken/wt/e2base1-p1')
FROZEN = Path('/data2/FreeToken/runs/dev_D16/t20_startup_cpu_5deba0293ed3/source_tools/equiv_suite/service_capture_startup.py')
FROZEN_SHA = '91102843e3d2b3464b78e7a0431165ab3ca32d488a59e17f8c818f7c2879ee12'


def _worker(tree, pause, fixed_stop, directory, ready):
    scheduler_path = Path(tree)/'python/freetoken/scheduler/scheduler.py'
    syntax = ast.parse(scheduler_path.read_bytes())
    cls = next(n for n in syntax.body if isinstance(n, ast.ClassDef) and n.name == 'Scheduler')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_receive_dev_messages')
    class Pause: pass
    class Cancel: pass
    namespace = {'DevPauseBackendMsg': Pause, 'DevPauseCancelBackendMsg': Cancel}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(scheduler_path), 'exec'), namespace)
    receive = namespace['_receive_dev_messages']
    class Scheduler:
        def __init__(self):
            self._dev_pending_pauses = []; self._dev_deferred_msgs = []; self.processed = []
            self._dev_pause_active = lambda: False
            self.receive_msg = lambda blocking: [object(), object()]
        def _process_one_msg(self, message): self.processed.append(message)
        def run_forever(self):
            if pause:
                receive(self, True)
            else:
                # Control arm: dispatch has already completed on the unchanged
                # default path. No claim about fake model computation is made.
                for message in self.receive_msg(True): self._process_one_msg(message)
            Path(directory, 'dispatch.json').write_text(json.dumps({
                'fixture_only': True, 'pause': pause, 'processed': len(self.processed),
                'deferred': len(self._dev_deferred_msgs),
                'scheduler_sha256': hashlib.sha256(scheduler_path.read_bytes()).hexdigest()}))
            ready.set()
            while True: time.sleep(.01)
        def shutdown(self):
            Path(directory, 'service_delivery.json').write_text(json.dumps({
                'fixture_only': True, 'shutdown_called': True, 'model_admitted': False}))
    scheduler = Scheduler()
    if fixed_stop:
        path = Path(__file__).parents[1]/'d16_native_capture_shutdown_v3.py'
        spec = importlib.util.spec_from_file_location('same_root_shutdown', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.run_with_sigterm_shutdown(scheduler)
    else:
        raw = FROZEN.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA
        function = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'run_scheduler')
        tail = function.body[-1]
        assert isinstance(tail, ast.Try) and not tail.finalbody
        assert ast.unparse(tail.handlers[0].type) == 'KeyboardInterrupt'
        # Execute the exact frozen try/except node, retaining default SIGTERM.
        exec(compile(ast.Module(body=[tail], type_ignores=[]), str(FROZEN), 'exec'),
             {'scheduler': scheduler, 'args': types.SimpleNamespace(tp_info=types.SimpleNamespace(is_primary=lambda: True))})


@pytest.mark.parametrize('tree,pause,fixed,processed,sealed', [
    (BASE, False, False, 2, False),
    (PATCH, False, False, 2, False),
    (BASE, True, False, 0, False),
    (PATCH, True, False, 2, False),
    (PATCH, True, True, 2, True),
])
def test_real_sigterm_stop_is_independent_of_pause_dispatch(tmp_path, tree, pause, fixed, processed, sealed):
    if os.name != 'posix' or not FROZEN.is_file(): pytest.skip('Linux frozen source required')
    context = multiprocessing.get_context('spawn'); ready = context.Event()
    child = context.Process(target=_worker, args=(str(tree), pause, fixed, str(tmp_path), ready))
    child.start()
    try:
        assert ready.wait(15), 'CPU worker did not reach post-dispatch stop boundary'
        observed = json.loads((tmp_path/'dispatch.json').read_text())
        assert observed['processed'] == processed
        assert observed['deferred'] == (2 if pause and tree == BASE else 0)
        os.kill(child.pid, signal.SIGTERM); child.join(10)
        assert child.exitcode == (0 if fixed else -signal.SIGTERM)
        assert (tmp_path/'service_delivery.json').is_file() == sealed
    finally:
        if child.is_alive(): child.kill(); child.join(10)
