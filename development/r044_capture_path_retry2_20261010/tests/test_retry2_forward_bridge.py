import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
torch = pytest.importorskip("torch")
from equiv_suite.service_capture import ServiceCaptureAdapter


SIGNATURE = "indeterminate: physical sampler history is missing or out of order"


def adapter(tmp_path):
    value = ServiceCaptureAdapter(tmp_path / "capture", expected_queries=[
        {"uid": 0, "generation_index": 0, "logical_label": "q0"},
        {"uid": 1, "generation_index": 0, "logical_label": "q1"},
    ], max_captures=32, max_bytes=1_000_000,
       process_identity={"pid": 1, "start_ticks": 2, "execution_id": "cpu"})
    value._bound = {uid: {"physical_event_identity": str(uid)} for uid in (0, 1)}
    return value


def forward(reqs, tokens, phase="decode"):
    batch = types.SimpleNamespace(reqs=reqs, phase=phase)
    input_ = types.SimpleNamespace(batch=batch)
    output = types.SimpleNamespace(next_tokens_cpu=torch.tensor(tokens, dtype=torch.int32))
    return batch, input_, output


def req(uid, cls="Req"):
    return type(cls, (), {"uid": uid, "device_len": 7})()


@pytest.mark.parametrize("terminal_kind", ["eos", "stop_string", "output_cap", "cache_hit"])
def test_real_lifecycle_postterminal_forward_is_retained_not_delivered(tmp_path, terminal_kind):
    value = adapter(tmp_path); request = req(0)
    value.deliveries = [{"uid": 0, "finished": True, "finish_reason": terminal_kind}]
    batch, input_, output = forward([request], [17]); value.observe_forward_start(input_)
    value.capture._deferred_history[id(batch)] = SIGNATURE
    value.observe_drained_forward(object(), (input_, output), {request})
    assert value.capture.errors == []
    assert value._bridge_extras == [{"uid": 0, "forward_sequence": 1, "sampled_token_id": 17,
                                     "delivered": False,
                                     "reason": "actual ForwardOutput after delivered terminal generation"}]


def test_real_lifecycle_chunked_prefill_is_explicit_un_delivered_physical_sample(tmp_path):
    value = adapter(tmp_path); chunk = req(0, "ChunkedReq")
    batch, input_, output = forward([chunk], [29], "prefill"); value.observe_forward_start(input_)
    value.capture._deferred_history[id(batch)] = SIGNATURE
    value.observe_drained_forward(object(), (input_, output), set())
    assert value.capture.errors == []
    assert value._bridge_extras[0]["reason"] == "actual ForwardOutput for ChunkedReq intermediate prefill"


def test_chunked_prefill_keeps_actual_logits_and_token_receipt(tmp_path):
    value = adapter(tmp_path)
    class Sampler:
        def sample(self, logits, _args): return logits.argmax(-1)
    class Engine:
        def __init__(self): self.sampler = Sampler()
        def forward_batch(self, batch, _args=None):
            return self.sampler.sample(torch.tensor([[1.0, 4.0]]), None)
    engine = Engine(); value.capture.attach(engine)
    chunk = req(0, "ChunkedReq"); chunk.input_ids = torch.tensor([9, 8], dtype=torch.int32)
    value.registry.bind_query(0, [9, 8, 7, 6], "physical-0")
    batch, input_, output = forward([chunk], [1], "prefill")
    value.observe_forward_start(input_); engine.forward_batch(batch)
    value.observe_drained_forward(object(), (input_, output), set())
    receipt = tmp_path / "capture" / "non_delivery" / "chunk-000001" / "receipt.json"
    assert receipt.is_file()
    saved = __import__("json").loads(receipt.read_text())
    assert saved["rows"][0]["sampled_token_id"] == 1
    assert saved["rows"][0]["actual_partial_context_ids"] == [9, 8]


def test_prefill_or_extra_step_without_real_terminal_proof_is_rejected(tmp_path):
    value = adapter(tmp_path); request = req(0)
    batch, input_, output = forward([request], [31]); value.observe_forward_start(input_)
    value.capture._deferred_history[id(batch)] = SIGNATURE
    value.observe_drained_forward(object(), (input_, output), set())
    assert value.capture.errors == [SIGNATURE] and value._bridge_extras == []


def test_uid_reorder_and_missing_physical_sample_are_rejected(tmp_path):
    value = adapter(tmp_path); first, second = req(0), req(1)
    value.deliveries = [{"uid": 0, "finished": True}, {"uid": 1, "finished": True}]
    batch, input_, output = forward([first, second], [2])  # actual ForwardOutput row count is short
    value.observe_forward_start(input_); value.capture._deferred_history[id(batch)] = SIGNATURE
    value.observe_drained_forward(object(), (input_, output), {first, second})
    assert any("token rows" in error for error in value.capture.errors)
    # A fresh snapshot rejects a changed request order even with two physical tokens.
    value = adapter(tmp_path); first, second = req(0), req(1)
    value.deliveries = [{"uid": 0, "finished": True}, {"uid": 1, "finished": True}]
    batch, input_, output = forward([first, second], [2, 3]); value.observe_forward_start(input_)
    batch.reqs[:] = [second, first]; value.capture._deferred_history[id(batch)] = SIGNATURE
    value.observe_drained_forward(object(), (input_, output), {first, second})
    assert any("UID order" in error for error in value.capture.errors)


def test_candidate_lifecycle_has_the_required_real_seams():
    candidate = Path("/data2/FreeToken/wt/e2base1-ordinary-rewind")
    if not candidate.is_dir():
        pytest.skip("candidate worktree is available only on the FreeToken host")
    engine = (candidate / "python/freetoken/engine/engine.py").read_text()
    scheduler = (candidate / "python/freetoken/scheduler/scheduler.py").read_text()
    chunk = (candidate / "python/freetoken/scheduler/prefill.py").read_text()
    assert engine.index("req.complete_one()") < engine.index("self.sampler.sample(batch_logits, args)")
    assert "ongoing_data = (forward_input, self._forward(forward_input))" in scheduler
    assert "self._process_last_data(last_data)" in scheduler
    assert "if isinstance(req, ChunkedReq):" in scheduler and "ChunkedReq should not be sampled" in chunk
