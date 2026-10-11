import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "t17_operator_startup.py"
SPEC = importlib.util.spec_from_file_location("t17_operator_startup", PATH)
startup = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(startup)


def test_configuration_requires_exact_runtime_binding(monkeypatch, tmp_path):
    for key in ("FT_T17_OPERATOR", "FT_T17_OPERATOR_QUERY_SHA", "FT_T17_OPERATOR_QUERY_TOKENS", "FT_T17_OPERATOR_BOUNDARY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="explicit"):
        startup._configuration()
    monkeypatch.setenv("FT_T17_OPERATOR", str(tmp_path))
    monkeypatch.setenv("FT_T17_OPERATOR_QUERY_SHA", "a" * 64)
    monkeypatch.setenv("FT_T17_OPERATOR_QUERY_TOKENS", "8257")
    monkeypatch.setenv("FT_T17_OPERATOR_BOUNDARY", "8192")
    assert startup._configuration() == (tmp_path, "a" * 64, 8257, 8192)


def test_startup_calls_frozen_hooks_once_and_binds_only_target_sha(monkeypatch, tmp_path):
    calls = []
    class Engine:
        def __init__(self, _config): self.model = SimpleNamespace(model=object()); calls.append("engine")
    class Scheduler:
        def _process_one_msg(self, msg): calls.append(("process", msg.uid))
    class IO:
        def _reply_tokenizer_rank0(self, messages): calls.append("reply"); return messages
    class Observer:
        bindings = {}
        def bind_query(self, uid, digest, size): self.bindings[str(uid)] = (digest, size)
    observer = Observer()
    observe = ModuleType("t17_operator_observe")
    observe.__file__ = str(PATH)
    observe.install = lambda *args, **kwargs: observer
    core = ModuleType("freetoken.core");core.get_global_ctx=lambda:SimpleNamespace(batch="actual-child-batch")
    engine = ModuleType("freetoken.engine.engine");engine.Engine=Engine
    scheduler = ModuleType("freetoken.scheduler.scheduler");scheduler.Scheduler=Scheduler
    io = ModuleType("freetoken.scheduler.io");io.SchedulerIOMixin=IO
    for name,module in {"t17_d14_startup":ModuleType("t17_d14_startup"),"t17_operator_observe":observe,"freetoken.core":core,"freetoken.engine.engine":engine,"freetoken.scheduler.scheduler":scheduler,"freetoken.scheduler.io":io}.items(): monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setenv("FT_T17_OPERATOR",str(tmp_path)); monkeypatch.setenv("FT_T17_OPERATOR_QUERY_TOKENS","3"); monkeypatch.setenv("FT_T17_OPERATOR_BOUNDARY","1")
    digest=startup.ids_sha([1,2,3]);monkeypatch.setenv("FT_T17_OPERATOR_QUERY_SHA",digest)
    startup.startup(); instance=Engine(None)
    class IDs:
        def __init__(self, values):self.values=values
        def tolist(self):return self.values
    UserMsg=type("UserMsg",(),{})
    target=UserMsg();target.uid=7;target.input_ids=IDs([1,2,3])
    donor=UserMsg();donor.uid=8;donor.input_ids=IDs([9])
    Scheduler()._process_one_msg(target);Scheduler()._process_one_msg(donor)
    assert calls==["engine",("process",7),("process",8)]
    assert observer.bindings=={"7":(digest,3)}


def test_cpu_worker_reports_installed_wrappers_without_cuda(monkeypatch):
    captured = []
    class Engine:
        def __init__(self): pass
    Engine.__init__.__name__ = "init_operator"
    class Scheduler:
        def _process_one_msg(self): pass
    Scheduler._process_one_msg.__name__ = "process_operator"
    class IO:
        def _reply_tokenizer_rank0(self): pass
    IO._reply_tokenizer_rank0.__name__ = "reply_operator"
    engine = ModuleType("freetoken.engine.engine");engine.Engine=Engine
    scheduler = ModuleType("freetoken.scheduler.scheduler");scheduler.Scheduler=Scheduler
    io = ModuleType("freetoken.scheduler.io");io.SchedulerIOMixin=IO
    exact = ModuleType("t17_d14_exact_ids")
    exact.cpu_probe = lambda queue: queue.put({"cuda_initialized":False,"uid":41})
    for name,module in {"t17_d14_exact_ids":exact,"freetoken.engine.engine":engine,"freetoken.scheduler.scheduler":scheduler,"freetoken.scheduler.io":io}.items(): monkeypatch.setitem(sys.modules,name,module)
    startup.cpu_worker(SimpleNamespace(put=captured.append))
    assert captured == [{"cuda_initialized":False,"uid":41,"operator_engine_init":"init_operator","operator_process":"process_operator","operator_reply":"reply_operator"}]
