import json
import pickle
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from equiv_suite.service_capture import ServiceCaptureAdapter, ServiceCaptureError, install_from_env
from equiv_suite.service_capture_startup import install_scheduler_capture
from freetoken.core import Batch, Req, SamplingParams
from freetoken.message import BatchBackendMsg, DetokenizeMsg, UserMsg


class Sampler:
    def __init__(self): self.calls = 0
    def sample(self, logits, args):
        self.calls += 1
        return logits.argmax(-1)


class Engine:
    def __init__(self): self.sampler = Sampler()
    def forward_batch(self, batch, logits):
        for req in batch.reqs: req.device_len += 1
        return self.sampler.sample(logits, None)


def query(uid, generation, label):
    return {"uid": uid, "generation_index": generation, "logical_label": label}


def adapter(tmp_path, queries):
    return ServiceCaptureAdapter(tmp_path / "service", expected_queries=queries, max_captures=8,
                                 max_bytes=1_000_000,
                                 process_identity={"pid": 1, "start_ticks": 2, "execution_id": "cpu-test"})


def user(uid, ids):
    return UserMsg(uid=uid, input_ids=torch.tensor(ids, dtype=torch.int32), sampling_params=SamplingParams())


def req(uid, ids):
    return SimpleNamespace(uid=uid, input_ids=torch.tensor(ids, dtype=torch.int32), device_len=len(ids))


def launch(engine, request, logits):
    return engine.forward_batch(SimpleNamespace(reqs=[request]), torch.tensor([logits], dtype=torch.float32))


def test_two_queries_delayed_delivery_and_overlap_extra_is_un_delivered_not_output_proof(tmp_path):
    instance = Engine(); capture = adapter(tmp_path, [query("donor", 0, "e1"), query("hit", 0, "e2")]).attach(instance)
    capture.admit_user_msg(user("donor", [1, 2]))
    capture.admit_user_msg(user("hit", [3, 4]))
    donor, hit = req("donor", [1, 2]), req("hit", [3, 4])
    launch(instance, donor, [9., 1.]); launch(instance, donor, [1., 9.])  # physical overlap sample remains undelivered
    launch(instance, hit, [1., 9.])
    capture.observe_detokenize(DetokenizeMsg(uid="hit", next_token=1, finished=True))
    capture.observe_detokenize(DetokenizeMsg(uid="donor", next_token=0, finished=True))
    assert capture.finalize()["terminal"] == "complete"
    report = json.loads((tmp_path / "service" / "service_delivery.json").read_text())
    assert report["admitted"] is False and report["terminal"] == "complete"
    assert report["deliveries"][0]["finished"] is True and report["deliveries"][1]["finished"] is True
    assert report["un_delivered_samples"] == [{"uid": "donor", "generation_index": 1, "sampled_token_id": 1, "delivered": False, "reason": "physical sample after delivered terminal generation"}]


@pytest.mark.parametrize("kind", ["missing", "duplicate", "mismatched"])
def test_delivery_gaps_duplicate_and_token_mismatch_fail_closed(tmp_path, kind):
    instance = Engine(); capture = adapter(tmp_path, [query("a", 0, "event")]).attach(instance)
    capture.admit_user_msg(user("a", [1, 2]))
    launch(instance, req("a", [1, 2]), [9., 1.])
    if kind == "duplicate":
        capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=0, finished=True))
        with pytest.raises(ServiceCaptureError, match="duplicate"):
            capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=0, finished=True))
    elif kind == "mismatched":
        with pytest.raises(ServiceCaptureError, match="does not match"):
            capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=1, finished=True))
    with pytest.raises(ServiceCaptureError):
        capture.finalize()
    assert json.loads((tmp_path / "service" / "service_delivery.json").read_text())["terminal"] == "failed"


def test_delivery_before_physical_sample_and_user_binding_mismatch_fail_closed(tmp_path):
    instance = Engine(); capture = adapter(tmp_path, [query("a", 0, "event")]).attach(instance)
    with pytest.raises(ServiceCaptureError, match="no bound"):
        capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=0, finished=True))
    with pytest.raises(ServiceCaptureError, match="no declared"):
        capture.admit_user_msg(user("wrong", [1, 2]))
    with pytest.raises(ServiceCaptureError):
        capture.finalize()


def test_env_entrypoint_is_inert_by_default_and_attaches_real_engine(tmp_path, monkeypatch):
    engine = Engine()
    assert install_from_env(engine) is None and engine.sampler.calls == 0
    expected = tmp_path / "expected.json"; expected.write_text(json.dumps([query("a", 0, "event")]))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path / "active"))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "2")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", "100000")
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "real-launcher-test")
    capture = install_from_env(engine)
    assert capture is not None and capture.capture.process_identity["execution_id"] == "real-launcher-test"
    capture.admit_user_msg(user("a", [1, 2]))
    launch(engine, req("a", [1, 2]), [9., 1.]); capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=0, finished=True))
    assert capture.finalize()["terminal"] == "complete"


class SchedulerShape:
    """The instance methods wrapped by the real Scheduler bootstrap."""
    def __init__(self):
        self.engine, self.processed, self.sent, self.shutdown_calls = Engine(), [], [], 0
        self.scheduled, self.schedule_calls = None, 0
    def _process_one_msg(self, message):
        self.processed.append(message)
        if isinstance(message, BatchBackendMsg):
            for item in message.data:
                self._process_one_msg(item)
        return "native-process-result"
    def send_result(self, reply):
        self.sent.append(reply)
        return "native-send-result"
    def shutdown(self):
        self.shutdown_calls += 1
        return "native-shutdown-result"
    def _schedule_next_batch(self):
        self.schedule_calls += 1
        return self.scheduled


def physical_req(uid, ids, table_idx, linear_slot_idx):
    request = Req(
        input_ids=torch.tensor(ids, dtype=torch.int32), table_idx=table_idx,
        cached_len=0, output_len=1, uid=uid, sampling_params=SamplingParams(),
        cache_handle=object(),
    )
    request.linear_slot_idx = linear_slot_idx
    return request


def physical_forward(slots):
    requests = [physical_req(uid, [uid, uid + 100], table_idx, linear_slot_idx)
                for uid, table_idx, linear_slot_idx in slots]
    batch = Batch(reqs=requests, phase="decode")
    batch.padded_reqs = list(requests)
    batch.active_table_idx = torch.tensor([item.table_idx for item in requests], dtype=torch.int64)
    return SimpleNamespace(batch=batch)


def test_startup_bootstrap_wraps_actual_message_shapes_and_seals_only_at_shutdown(tmp_path, monkeypatch):
    expected = tmp_path / "expected.json"; expected.write_text(json.dumps([query(11, 0, "actual-event")]))
    destination = tmp_path / "dev_D16" / "service"
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(destination))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "2")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", "100000")
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "startup-cpu")
    scheduler = SchedulerShape(); capture = install_scheduler_capture(scheduler)
    scheduled = physical_forward([(11, 7, 8)]); scheduler.scheduled = scheduled
    assert scheduler._schedule_next_batch() is scheduled
    msg = UserMsg(uid=11, input_ids=torch.tensor([1, 2], dtype=torch.int32), sampling_params=SamplingParams())
    assert scheduler._process_one_msg(msg) == "native-process-result" and scheduler.processed == [msg]
    launch(scheduler.engine, req(11, [1, 2]), [9., 1.])
    reply = [DetokenizeMsg(uid=11, next_token=0, finished=True)]
    assert scheduler.send_result(reply) == "native-send-result" and scheduler.sent == [reply]
    assert not (destination / "service_delivery.json").exists()  # never seal after donor/first delivery
    assert scheduler.shutdown() == "native-shutdown-result" and scheduler.shutdown_calls == 1
    report = json.loads((destination / "service_delivery.json").read_text())
    assert capture is not None and report["terminal"] == "complete" and report["deliveries"][0]["next_token"] == 0
    assert report["scheduler_batches"][0]["requests"] == [{
        "uid": 11, "input_ids_sha256": "d1188e1231b978cc3cf25a643396fafd41a85d3e458ed92c6d0355de8d1cd9eb",
        "table_idx": 7, "linear_slot_idx": 8,
    }]


def test_startup_send_failure_is_preserved_and_only_records_diagnostic(tmp_path, monkeypatch):
    expected = tmp_path / "expected.json"; expected.write_text(json.dumps([query(11, 0, "actual-event")]))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path / "dev_D16" / "service"))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "2")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", "100000")
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "startup-cpu")
    scheduler = SchedulerShape()
    def broken_send(reply):
        scheduler.sent.append(reply)
        raise RuntimeError("native queue failure")
    scheduler.send_result = broken_send
    install_scheduler_capture(scheduler)
    with pytest.raises(RuntimeError, match="native queue failure"):
        scheduler.send_result([DetokenizeMsg(uid=11, next_token=0, finished=True)])
    scheduler.shutdown()
    report = json.loads((tmp_path / "dev_D16" / "service" / "service_delivery.json").read_text())
    assert report["terminal"] == "failed" and any("send_result raised" in error for error in report["errors"])


def test_preterminal_extra_fails_even_when_full_sampler_manifest_is_sealed(tmp_path):
    instance = Engine(); capture = adapter(tmp_path, [query("a", 0, "logic")]).attach(instance)
    capture.admit_user_msg(user("a", [1, 2])); request = req("a", [1, 2])
    launch(instance, request, [9., 1.]); launch(instance, request, [1., 9.])
    capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=0, finished=False))
    with pytest.raises(ServiceCaptureError, match="terminal"):
        capture.finalize()
    manifest = json.loads((tmp_path / "service" / "sampler" / "manifest.json").read_text())
    assert manifest["terminal"] == "complete" and len(manifest["captures"]) == 2


def test_logical_label_does_not_change_physical_event_and_admission_tamper_rejects(tmp_path):
    identity = {"pid": 1, "start_ticks": 2, "execution_id": "cpu-test"}
    first = ServiceCaptureAdapter(tmp_path / "one", expected_queries=[query("a", 0, "label-one")], max_captures=2, max_bytes=1_000_000, process_identity=identity).attach(Engine())
    second = ServiceCaptureAdapter(tmp_path / "two", expected_queries=[query("a", 0, "label-two")], max_captures=2, max_bytes=1_000_000, process_identity=identity).attach(Engine())
    assert first.admit_user_msg(user("a", [1, 2])) == second.admit_user_msg(user("a", [1, 2]))
    instance = Engine(); capture = adapter(tmp_path / "tamper", [query("a", 0, "logic")]).attach(instance)
    capture.admit_user_msg(user("a", [1, 2])); launch(instance, req("a", [1, 2]), [9., 1.])
    receipt = tmp_path / "tamper" / "service" / "admissions" / "admission-000001.json"
    receipt.write_text(receipt.read_text().replace('"uid":"a"', '"uid":"b"'))
    capture.observe_detokenize(DetokenizeMsg(uid="a", next_token=0, finished=True))
    with pytest.raises(ServiceCaptureError, match="SHA"):
        capture.finalize()


def test_real_batch_backend_recurses_and_startup_module_is_spawn_picklable(tmp_path, monkeypatch):
    expected = tmp_path / "expected.json"; expected.write_text(json.dumps([query(1, 0, "one"), query(2, 0, "two")]))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path / "dev_D16" / "batch"))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "4")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", "100000")
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "batch-cpu")
    scheduler = SchedulerShape(); install_scheduler_capture(scheduler)
    messages = [UserMsg(uid=1, input_ids=torch.tensor([1, 2], dtype=torch.int32), sampling_params=SamplingParams()), UserMsg(uid=2, input_ids=torch.tensor([3, 4], dtype=torch.int32), sampling_params=SamplingParams())]
    scheduler._process_one_msg(BatchBackendMsg(data=messages))
    assert scheduler.processed == [BatchBackendMsg(data=messages), *messages]
    from equiv_suite.service_capture_startup import run_scheduler
    assert pickle.loads(pickle.dumps(run_scheduler)) is run_scheduler


@pytest.mark.parametrize("slot_count", [2, 4])
def test_scheduler_observer_records_actual_core_batch_and_returns_native_forward_identity(tmp_path, monkeypatch, slot_count):
    expected = tmp_path / "expected.json"; expected.write_text(json.dumps([query(1, 0, "one")]))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path / "dev_D16" / "batch"))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "4")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", "100000")
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "batch-cpu")
    scheduler = SchedulerShape()
    forward = physical_forward([(index + 1, index + 20, index + 40) for index in range(slot_count)])
    scheduler.scheduled = forward
    capture = install_scheduler_capture(scheduler)
    assert scheduler._schedule_next_batch() is forward and scheduler.schedule_calls == 1
    observed = capture.scheduler_batches
    assert len(observed) == 1
    event = observed[0]
    assert event["scheduler_sequence"] == 1 and event["phase"] == "decode"
    assert event["physical_size"] == slot_count and event["padded_size"] == slot_count
    assert event["active_table_idx"] == list(range(20, 20 + slot_count))
    assert [item["uid"] for item in event["requests"]] == list(range(1, slot_count + 1))
    assert [item["linear_slot_idx"] for item in event["requests"]] == list(range(40, 40 + slot_count))
    assert all(len(item["input_ids_sha256"]) == 64 for item in event["padded_requests"])


def test_scheduler_observer_failure_is_diagnostic_and_never_changes_native_return(tmp_path, monkeypatch):
    expected = tmp_path / "expected.json"; expected.write_text(json.dumps([query(1, 0, "one")]))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path / "dev_D16" / "batch"))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", str(expected))
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "4")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_MAX_BYTES", "100000")
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "batch-cpu")
    scheduler = SchedulerShape(); native_forward = SimpleNamespace(batch=object()); scheduler.scheduled = native_forward
    capture = install_scheduler_capture(scheduler)
    assert scheduler._schedule_next_batch() is native_forward and scheduler.schedule_calls == 1
    assert capture.scheduler_batches == []
    assert any("Scheduler batch observation failed" in error for error in capture.errors)


def test_scheduler_capture_is_inert_without_opt_in_environment(monkeypatch):
    for key in ("FT_D16_SERVICE_CAPTURE_DIR", "FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", "FT_D16_SERVICE_CAPTURE_MAX_CAPTURES", "FT_D16_SERVICE_CAPTURE_MAX_BYTES", "FT_D16_EXECUTION_ID"):
        monkeypatch.delenv(key, raising=False)
    scheduler = SchedulerShape(); native_forward = physical_forward([(1, 2, 3)]); scheduler.scheduled = native_forward
    original = scheduler._schedule_next_batch
    assert install_scheduler_capture(scheduler) is None
    assert scheduler._schedule_next_batch.__func__ is original.__func__
    assert scheduler._schedule_next_batch.__self__ is original.__self__
    assert scheduler._schedule_next_batch() is native_forward and scheduler.schedule_calls == 1
