"""CPU integration coverage for R040d's native-compatible capture interfaces."""
from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from r040d_d16_native_capture_shutdown_v4 import NativeCaptureShutdownError, read_sealed_service_delivery
from r040d_d16_sampler_capture import install as install_sampler
from r040d_d16_native_service_capture_startup_v2 import install_scheduler_capture, main, run_scheduler
from r040d_d16_native_service_capture_v2 import ServiceCaptureAdapter, ServiceCaptureError


@dataclass
class UserMsg:
    uid: int
    input_ids: list[int]


@dataclass
class DetokenizeMsg:
    uid: int
    next_token: int
    finished: bool


@dataclass
class Request:
    uid: int
    device_len: int


@dataclass
class Batch:
    reqs: list[Request]
    sampled: list[int]


class Sampler:
    def sample(self, logits, _args): return list(logits)


class Engine:
    def __init__(self): self.sampler = Sampler()
    def forward_batch(self, batch, args): return self.sampler.sample(batch.sampled, args)


class ForwardInput:
    def __init__(self, batch): self.batch = batch


class Scheduler:
    def __init__(self): self.engine, self.processed, self.sent, self.shutdowns = Engine(), [], [], 0
    def _process_one_msg(self, message): self.processed.append(message); return "processed"
    def send_result(self, reply): self.sent.extend(reply if isinstance(reply, list) else [reply]); return "sent"
    def _prepare_batch(self, batch): return ForwardInput(batch)
    def shutdown(self): self.shutdowns += 1


def expected():
    return [{"uid": uid, "generation_index": generation, "logical_label": f"u{uid}"}
            for uid in range(4) for generation in range(128)]


def test_scheduler_hook_uses_real_prepare_sample_send_interfaces_and_seals(tmp_path):
    scheduler = Scheduler()
    adapter = ServiceCaptureAdapter(tmp_path / "capture", expected_queries=expected())
    adapter.attach(scheduler.engine)
    assert install_scheduler_capture(scheduler, user_message_type=UserMsg, detokenize_message_type=DetokenizeMsg,
                                     adapter=adapter) is adapter
    for uid in range(4): scheduler._process_one_msg(UserMsg(uid, [uid + 1] * (512 + uid)))
    for generation in range(128):
        order = [(generation + shift) % 4 for shift in (1, 3, 0, 2)]
        batch = Batch([Request(uid, 512 + uid + generation) for uid in order], [uid * 1000 + generation for uid in order])
        assert scheduler._prepare_batch(batch).batch is batch
        scheduler.engine.forward_batch(batch, None)
        scheduler.send_result([DetokenizeMsg(uid, uid * 1000 + generation, generation == 127) for uid in reversed(order)])
    scheduler.shutdown()
    report = json.loads((tmp_path / "capture" / "service_delivery.json").read_text(encoding="utf-8"))
    assert report["terminal"] == "complete" and report["verified_count"] == 512
    assert len(adapter.prepared_batches) == 128
    assert scheduler.shutdowns == 1
    assert read_sealed_service_delivery(tmp_path) == report


def test_missing_delivery_reader_names_arm_path_counts_and_first_missing(tmp_path):
    adapter = ServiceCaptureAdapter(tmp_path / "arm-a" / "capture", expected_queries=[
        {"uid": 9, "generation_index": 0, "logical_label": "u9"},
        {"uid": 9, "generation_index": 1, "logical_label": "u9"}])
    class OneEngine:
        def __init__(self): self.sampler = Sampler()
        def forward_batch(self, batch, args): return self.sampler.sample(batch.sampled, args)
    engine = OneEngine(); adapter.attach(engine); adapter.admit_user_msg(UserMsg(9, [1])); engine.forward_batch(Batch([Request(9, 1)], [7]), None)
    with pytest.raises(ServiceCaptureError, match="expected delivery count"):
        adapter.finalize()
    with pytest.raises(NativeCaptureShutdownError, match=r"arm=.*arm-a.*service_delivery.json.*expected=2.*verified=0.*uid=9,generation=0"):
        read_sealed_service_delivery(tmp_path / "arm-a")


def test_scheduler_hook_rejects_partial_native_rows_before_delivery(tmp_path):
    scheduler = Scheduler(); adapter = ServiceCaptureAdapter(tmp_path / "capture", expected_queries=[
        {"uid": uid, "generation_index": 0, "logical_label": f"u{uid}"} for uid in range(4)])
    adapter.attach(scheduler.engine)
    install_scheduler_capture(scheduler, user_message_type=UserMsg, detokenize_message_type=DetokenizeMsg, adapter=adapter)
    for uid in range(4): scheduler._process_one_msg(UserMsg(uid, [uid + 1]))
    with pytest.raises(Exception, match="rows do not equal"):
        scheduler.engine.forward_batch(Batch([Request(uid, 1) for uid in range(4)], [1, 2, 3]), None)


def test_sampler_install_and_finish_compatibility_interface():
    engine = Engine(); capture = install_sampler(engine)
    capture.bind_query(7, 1)
    engine.forward_batch(Batch([Request(7, 1)], [19]), None)
    capture.finish({7: 1})


def test_main_installs_worker_replacement_only_for_capture_environment(monkeypatch):
    launch = types.ModuleType("freetoken.server.launch")
    calls = []
    launch._run_scheduler = object()
    launch.launch_server = lambda argv=None: calls.append(argv)
    server = types.ModuleType("freetoken.server"); server.launch = launch
    freetoken = types.ModuleType("freetoken"); freetoken.server = server
    monkeypatch.setitem(sys.modules, "freetoken", freetoken)
    monkeypatch.setitem(sys.modules, "freetoken.server", server)
    monkeypatch.setitem(sys.modules, "freetoken.server.launch", launch)
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", "/tmp/dev_D16/capture")
    main(["serve"])
    assert launch._run_scheduler is run_scheduler and calls == [["serve"]]


def test_run_scheduler_real_entry_signature_seals_capture_on_normal_return(tmp_path, monkeypatch):
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps([{"uid": 0, "generation_index": 0, "logical_label": "u0"}]), encoding="utf-8")
    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class LiveScheduler(Scheduler):
        def sync_all_ranks(self): pass
        def run_forever(self):
            self._process_one_msg(UserMsg(0, [1]))
            batch = Batch([Request(0, 1)], [77])
            self._prepare_batch(batch)
            self.engine.forward_batch(batch, None)
            self.send_result([DetokenizeMsg(0, 77, True)])
    live = LiveScheduler()
    launch = types.ModuleType("freetoken.server.launch"); launch._detach_process_group = lambda: None; launch._report_startup_error = lambda *_: pytest.fail("startup error")
    scheduler_module = types.ModuleType("freetoken.scheduler"); scheduler_module.Scheduler = lambda _args: live
    gpu = types.ModuleType("freetoken.gpu_select"); gpu.set_assigned_gpu = lambda _gpu: None
    progress = types.ModuleType("freetoken.utils.progress"); progress.set_progress_sink = lambda _sink: None
    message = types.ModuleType("freetoken.message"); message.UserMsg = UserMsg; message.DetokenizeMsg = DetokenizeMsg
    server = types.ModuleType("freetoken.server"); server.launch = launch
    freetoken = types.ModuleType("freetoken"); freetoken.server = server
    monkeypatch.setitem(sys.modules, "freetoken", freetoken); monkeypatch.setitem(sys.modules, "freetoken.server", server)
    monkeypatch.setitem(sys.modules, "freetoken.server.launch", launch); monkeypatch.setitem(sys.modules, "freetoken.scheduler", scheduler_module)
    monkeypatch.setitem(sys.modules, "freetoken.gpu_select", gpu); monkeypatch.setitem(sys.modules, "freetoken.utils.progress", progress); monkeypatch.setitem(sys.modules, "freetoken.message", message)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(inference_mode=Context))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path / "dev_D16" / "capture"))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected_path))
    tp = types.SimpleNamespace(size=1, rank=0, is_primary=lambda: True)
    args = types.SimpleNamespace(shell_mode=False, gpu_assigned=("0",), gpu=(), tp_info=tp, silent_output=False)
    class Queue:
        def __init__(self): self.rows = []
        def put(self, value): self.rows.append(value)
    ready = Queue(); run_scheduler(args, ready)
    report = json.loads((tmp_path / "dev_D16" / "capture" / "service_delivery.json").read_text(encoding="utf-8"))
    assert ready.rows == ["Scheduler is ready"] and live.shutdowns == 1 and report["terminal"] == "complete"
