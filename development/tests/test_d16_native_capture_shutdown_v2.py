import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("d16_shutdown_v2", ROOT / "d16_native_capture_shutdown_v2.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def _spawn_scheduler(capture_dir, ready, result):
    class Scheduler:
        def __init__(self): self.calls = 0
        def run_forever(self):
            ready.set()
            while True: time.sleep(0.02)
        def shutdown(self):
            self.calls += 1
            (Path(capture_dir) / "service_delivery.json").write_text(json.dumps({"terminal": "complete", "shutdown_calls": self.calls}))
    scheduler = Scheduler()
    try:
        graceful = module.run_with_sigterm_shutdown(scheduler)
        result.put(("ok", graceful, scheduler.calls))
    except BaseException as error:
        result.put(("error", type(error).__name__, scheduler.calls))


def test_spawn_sigterm_seals_service_delivery_exactly_once(tmp_path):
    if sys.platform != "linux":
        pytest.skip("real SIGTERM spawn semantics are Linux-only")
    capture = tmp_path / "capture"; capture.mkdir()
    ctx = multiprocessing.get_context("spawn")
    ready, result = ctx.Event(), ctx.Queue()
    child = ctx.Process(target=_spawn_scheduler, args=(str(capture), ready, result))
    child.start()
    try:
        assert ready.wait(15)
        os.kill(child.pid, signal.SIGTERM)
        assert result.get(timeout=15) == ("ok", True, 1)
        child.join(15)
        assert child.exitcode == 0
    finally:
        if child.is_alive(): child.kill(); child.join(10)
    assert json.loads((capture / "service_delivery.json").read_text()) == {"terminal": "complete", "shutdown_calls": 1}


def test_non_signal_error_propagates_after_one_shutdown():
    class Scheduler:
        def __init__(self): self.calls = 0
        def run_forever(self): raise ValueError("source failure")
        def shutdown(self): self.calls += 1
    scheduler = Scheduler()
    with pytest.raises(ValueError, match="source failure"):
        module.run_with_sigterm_shutdown(scheduler)
    assert scheduler.calls == 1


def test_missing_delivery_is_explicit_harness_failure(tmp_path):
    with pytest.raises(module.NativeCaptureShutdownError, match="was not sealed"):
        module.read_sealed_service_delivery(tmp_path)


def test_keyboard_interrupt_seals_once_without_signal():
    class Scheduler:
        def __init__(self): self.calls = 0
        def run_forever(self): raise KeyboardInterrupt
        def shutdown(self): self.calls += 1
    scheduler = Scheduler()
    assert module.run_with_sigterm_shutdown(scheduler) is True
    assert scheduler.calls == 1


def test_install_composes_v3_parking_before_worker_replacement(monkeypatch):
    import types
    exact=types.SimpleNamespace(calls=0, install=lambda: setattr(exact,"calls",exact.calls+1))
    launch=types.SimpleNamespace(_run_scheduler=None)
    monkeypatch.setitem(sys.modules,"d16_exact_service_startup_v3",exact)
    server=types.ModuleType("freetoken.server");server.launch=launch
    monkeypatch.setitem(sys.modules,"freetoken.server",server)
    module.install()
    assert exact.calls==1 and launch._run_scheduler is module.run_scheduler
