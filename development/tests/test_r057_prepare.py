import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import runpy
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


def _spawn_mp_main(script: str, snapshot: str, queue) -> None:
    """CPU-only fake product validates the real spawn import name path."""
    torch = types.ModuleType("torch")
    calls = []
    memory = types.SimpleNamespace(_record_memory_history=lambda **kwargs: calls.append(kwargs), _dump_snapshot=lambda _path: None)
    torch.cuda = types.SimpleNamespace(memory=memory, mem_get_info=lambda _device: (1, 2), memory_allocated=lambda _device: 0, memory_reserved=lambda _device: 0)
    engine_pkg, engine_mod = types.ModuleType("freetoken.engine"), types.ModuleType("freetoken.engine.engine")
    scheduler_pkg, scheduler_mod = types.ModuleType("freetoken.scheduler"), types.ModuleType("freetoken.scheduler.scheduler")
    io_mod = types.ModuleType("freetoken.scheduler.io")
    class Engine:
        def __init__(self):
            pass
    class Scheduler:
        def _process_one_msg(self, message):
            return message
        def _forward(self, *args, **kwargs):
            return None
    class SchedulerIOMixin:
        def _reply_tokenizer_rank0(self, messages):
            return messages
    engine_mod.Engine, scheduler_mod.Scheduler, io_mod.SchedulerIOMixin = Engine, Scheduler, SchedulerIOMixin
    sys.modules.update({"torch": torch, "freetoken": types.ModuleType("freetoken"), "freetoken.engine": engine_pkg,
                        "freetoken.engine.engine": engine_mod, "freetoken.scheduler": scheduler_pkg,
                        "freetoken.scheduler.scheduler": scheduler_mod, "freetoken.scheduler.io": io_mod})
    os.environ["R057_SNAPSHOT_DIR"] = snapshot
    os.environ["R057_SERVICE_BIRTH"] = json.dumps({"pid": os.getpid()})
    runpy.run_path(script, run_name="__mp_main__")
    # runpy owns the function globals; patch the installed hook's real module
    # dictionary because this CPU-only spawn process has no /proc tree.
    Engine.__init__.__globals__["_birth"] = lambda: {"pid": os.getpid(), "start_ticks": 1, "execution_id": f"{os.getpid()}:1", "pgid": 1, "session": 1}
    queue.put({"history_before_engine": list(calls), "snapshot_before_engine": Path(snapshot).exists(),
               "hooked": Scheduler._process_one_msg.__name__ == "observed_process"})
    Engine()
    queue.put({"history_after_engine": list(calls), "snapshot_after_engine": Path(snapshot).is_dir()})


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "r057_oom_diagnostic_prepare.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_four_arms_have_required_truth_table(monkeypatch, tmp_path):
    tool = load("r057_truth_table")
    monkeypatch.setattr(tool, "load_d07", lambda: type("D", (), {"clean_environment": staticmethod(lambda *_a, **_k: {"CUDA_VISIBLE_DEVICES": "0", "PYTHONPATH": "p", "VIRTUAL_ENV": "v"}), "serve_argv": staticmethod(lambda port: ["ft", "serve", "--port", str(port), "--memory-ratio", "0.88", "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--cuda-graph-max-bs", "2"])})())
    plans = [tool.arm_plan(arm, 40000 + index, tmp_path) for index, arm in enumerate(tool.ARMS)]
    assert [(p["environment"].get("FT_DEV_ROUTE_TRACE") is not None, p["environment"].get("FT_DEV_PAUSE_ENDPOINT") == "1") for p in plans] == [(True, False), (False, True), (True, True), (False, False)]
    assert [p["ft_argv"][p["ft_argv"].index("--cuda-graph-max-bs") + 1] for p in plans] == ["2", "2", "2", "0"]
    assert all(p["record_memory_history"] for p in plans)


def test_diff_declares_single_variable_comparisons():
    tool = load("r057_diff")
    a, b, c, d = tool.ARMS
    assert tool.serve_args_diff(a)["differences"] == {"trace": {"baseline": False, "actual": True}}
    assert tool.serve_args_diff(b)["differences"] == {"pause": {"baseline": False, "actual": True}}
    assert tool.serve_args_diff(c)["differences"] == {"trace": {"baseline": False, "actual": True}, "pause": {"baseline": False, "actual": True}}
    assert tool.serve_args_diff(d)["differences"] == {"cuda_graph_max_bs": {"baseline": 2, "actual": 0}}


def test_wrapper_is_same_process_history_hook():
    wrapper = (ROOT / "r057_memory_history_startup.py").read_text(encoding="utf-8")
    assert "_record_memory_history(enabled=\"all\", context=\"all\", stacks=\"all\", max_entries=MAX_HISTORY_ENTRIES)" in wrapper
    assert "_dump_snapshot" in wrapper
    assert "from freetoken.cli import main as ft_main" in wrapper
    assert "Scheduler._process_one_msg = observed_process" in wrapper
    assert "Scheduler._forward = observed_forward" in wrapper
    assert 'type(message).__name__ == "UserMsg"' in wrapper
    assert 'if __name__ == "__mp_main__"' in wrapper
    assert "def observed_forward(self, *args, **kwargs)" in wrapper


def test_snapshot_failure_is_recorded_without_hiding_request_error(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("r057_wrapper", ROOT / "r057_memory_history_startup.py")
    wrapper = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(wrapper)
    monkeypatch.setattr(wrapper, "_snapshot", lambda *_args: (_ for _ in ()).throw(RuntimeError("snapshot failed")))
    events = tmp_path / "events.jsonl"
    wrapper._safe_snapshot(events, tmp_path, "request_error")
    row = json.loads(events.read_text(encoding="utf-8"))
    assert row["event"] == "snapshot_error" and row["requested_event"] == "request_error"


def test_real_spawn_mp_main_defers_cuda_history_until_model_engine(tmp_path):
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    child = context.Process(target=_spawn_mp_main, args=(str(ROOT / "r057_memory_history_startup.py"), str(tmp_path / "snapshots"), queue))
    child.start()
    child.join(20)
    assert child.exitcode == 0
    installed, activated = queue.get(timeout=2), queue.get(timeout=2)
    assert installed == {"history_before_engine": [], "snapshot_before_engine": False, "hooked": True}
    assert activated == {"history_after_engine": [{"enabled": "all", "context": "all", "stacks": "all", "max_entries": 200_000}],
                         "snapshot_after_engine": True}


def test_cold_payload_is_saved_before_oom_from_urlopen(monkeypatch, tmp_path):
    tool = load("r057_payload_before_oom")
    directory = tmp_path / "arm"
    directory.mkdir()
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("CUDA out of memory")))
    def invoke(_worktree, _port, _rid, _output):
        tool.urllib.request.urlopen(type("Request", (), {"data": b'{\"cold\":true}'})())
    with __import__("pytest").raises(RuntimeError, match="out of memory"):
        tool.invoke_bound_cold(type("D", (), {"invoke_cold_eq": staticmethod(invoke)})(), directory, 41234)
    payload = directory / "cold_request_payload.json"
    assert payload.read_bytes() == b'{"cold":true}'
    assert json.loads((directory / "cold_request_binding.json").read_text())["payload_sha256"] == tool.sha256(payload)


def test_four_independent_lifecycles_continue_after_oom(monkeypatch, tmp_path):
    tool = load("r057_lifecycle")
    calls = []
    monkeypatch.setattr(tool, "dynamic_port", lambda: 41000 + len(calls))
    monkeypatch.setattr(tool, "arm_plan", lambda arm, port, root: {"arm": arm["name"], "port": port})
    monkeypatch.setattr(tool, "_validate_args", lambda *_args: None)
    monkeypatch.setattr(tool, "_cleanup", lambda _d, process, directory, _active: calls.append((process.pid, directory.name)))
    monkeypatch.setattr(tool, "_start_arm", lambda _d, directory, plan: type("P", (), {"pid": len(calls) + 1})())
    def cold(_d, directory, _port):
        if "C_trace" in str(directory):
            raise RuntimeError("CUDA out of memory")
    monkeypatch.setattr(tool, "invoke_bound_cold", cold)
    monkeypatch.setattr(tool, "_require_32064_usage", lambda _path: None)
    monkeypatch.setattr(tool, "snapshot_evidence", lambda _directory, event: {"event": event, "sha256": "x"})
    d07 = type("D", (), {"verify_frozen_cold_helpers": staticmethod(lambda: {"cold_eq_raw_sha256": "x", "probe_raw_sha256": "y"})})()
    result = tool.run_arms(d07, tmp_path)
    assert [row["status"] for row in result] == ["completed", "completed", "oom", "completed"]
    assert len(calls) == 4


def test_main_run_dispatches_owned_controller(monkeypatch, capsys):
    tool = load("r057_main_run")
    monkeypatch.setattr(tool, "execute", lambda **kwargs: {"controller": kwargs})
    assert tool.main(["--run"]) == 0
    assert '"owned_child": false' in capsys.readouterr().out


def test_self_test_has_no_model_or_network_dependency(capsys):
    tool = load("r057_self_test")
    tool.self_test()
    assert "SELFTEST PASS" in capsys.readouterr().out


def test_shared_sources_can_be_explicit_readonly_pointers(monkeypatch, tmp_path):
    monkeypatch.setenv("R057_D07_SOURCE", str(tmp_path / "d07.py"))
    (tmp_path / "d07.py").write_text("", encoding="utf-8")
    tool = load("r057_source_pointers")
    assert tool.D07_SOURCE == tmp_path / "d07.py"
