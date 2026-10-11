"""Actual candidate loop/mixer/head and D03 collector, using CPU fixture tensors."""
import hashlib
import json
import os
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires the candidate and pinned D03 Linux modules", allow_module_level=True)

import torch
from freetoken.kvcache import linear_state_pool
from freetoken.layers import embedding
from freetoken.models.qwen4_exp import model as native_model
from freetoken.models.qwen4_exp.hc import GatedResidual

from prompt_tail import PromptTailCapture, load_d03
from segment_capture import install_prefill_segment_capture


def batch(start, end, uid=0):
    req = SimpleNamespace(uid=uid, cached_len=start, device_len=end, extend_len=end-start, linear_slot_idx=0)
    return SimpleNamespace(reqs=[req], padded_reqs=[req], input_ids=torch.arange(start, end),
                           is_prefill=True, size=1, mm_embeds=None,
                           attn_metadata=SimpleNamespace(get_last_indices=lambda _: torch.tensor([end-start-1])))


def fixture(tmp_path, monkeypatch, *, maximum=1000000, length=12, k=4):
    d03 = load_d03(os.environ["FT_D12_D03_ROOT"])
    state_root, destination = tmp_path / "states", tmp_path / "logits"
    monkeypatch.setattr(linear_state_pool, "DUMP_PATH", str(state_root))
    monkeypatch.setenv("FT_DEV_LOGITS_DUMP", str(destination))
    pool = linear_state_pool.LinearStatePool.__new__(linear_state_pool.LinearStatePool)
    pool.conv_states = torch.arange(8, dtype=torch.bfloat16).reshape(2, 1, 4)
    pool.recurrent_states = torch.arange(8, dtype=torch.float32).reshape(2, 1, 4)
    pool.slot_states = {"ple_conv": torch.arange(4, dtype=torch.float32).reshape(1, 1, 4),
                        "ple_ngram_ctx": torch.arange(4).reshape(1, 1, 4)}
    pool._group = SimpleNamespace(layer_ids=[0, 1])
    pool._state_layer_index = {"ple_conv": {1: 0}, "ple_ngram_ctx": {}}

    class Context:
        _batch = None
        @property
        def batch(self): return self._batch
    ctx = Context()
    ctx.linear_state_pool = pool
    monkeypatch.setattr(native_model, "get_global_ctx", lambda: ctx)
    monkeypatch.setattr(embedding, "get_global_ctx", lambda: ctx)
    order, mix_shapes = [], []

    class Layer:
        ple = None
        def __init__(self, index): self.index = index
        def forward(self, hidden, current):
            order.append((self.index, current.reqs[0].cached_len, current.reqs[0].device_len))
            return hidden + (self.index + 1) * 0.125

    mixer = GatedResidual.__new__(GatedResidual)
    mixer.hc_count, mixer.hidden_size, mixer.use_combine = 2, 2, False
    mixer.hc_norm = SimpleNamespace(weight=torch.zeros(4), eps=1e-6)
    down, up = torch.arange(8).float().reshape(4, 2) / 20, torch.arange(8).float().reshape(2, 4) / 30
    mixer.input_mix_weight_down = SimpleNamespace(forward=lambda x: x @ down)
    mixer.input_mix_weight_up = SimpleNamespace(forward=lambda x: x @ up)
    native_mix = mixer.mix
    def count_mix(hidden):
        mix_shapes.append(tuple(hidden.shape))
        return native_mix(hidden)
    mixer.mix = count_mix
    embed = lambda ids: torch.stack((ids.float() + 1, ids.float() * 0.25 + 2), dim=1)
    body = native_model.Qwen4ExpModel.__new__(native_model.Qwen4ExpModel)
    body.hc_count, body._ple = 2, ()
    body.embed_tokens = SimpleNamespace(forward=embed)
    body.layers = SimpleNamespace(op_list=[Layer(0), Layer(1)])
    body.hyper_connection_mixer = mixer
    head = embedding.ParallelLMHead.__new__(embedding.ParallelLMHead)
    head.tp_size, head.num_embeddings = 1, 5
    head.tied_embedding = SimpleNamespace(weight=torch.arange(10).float().reshape(5, 2) / 7)
    head.bias = None
    llm = native_model.Qwen4ExpForCausalLM.__new__(native_model.Qwen4ExpForCausalLM)
    llm.model, llm.lm_head = body, head
    engine = SimpleNamespace(ctx=ctx, model=llm, linear_state_pool=pool)
    def forward(outer, children=None):
        ctx._batch = outer
        try:
            if children is None: return llm.forward()
            return llm.forward_layer_major(children)
        finally:
            ctx._batch = None
    engine.forward_batch = forward
    events, holder = [], {}
    def emit(event):
        events.append(event)
        if "capture" in holder:
            holder["capture"].observe_state(event)
    provider, restore_segment = install_prefill_segment_capture(SimpleNamespace(engine=engine), state_root, emit,
                                                               allowed_uids=(0,))
    ids = list(range(length))
    binding = {"bundle_sha256": "cpu-fixture", "requests": [{"uid": 0, "input_ids": ids,
                "input_ids_json_sha256": hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest(),
                "payload_sha256": "cpu-fixture", "max_tokens": 2048, "temperature": 0}]}
    capture = PromptTailCapture(engine, binding, state_root, destination, d03, provider, events.append,
                                max_hidden_bytes=maximum, k=k)
    holder["capture"] = capture
    return SimpleNamespace(engine=engine, capture=capture, d03=d03, events=events, order=order,
                           mix_shapes=mix_shapes, native_mix=native_mix, embed=embed, root=destination,
                           restore_segment=restore_segment, binding=binding)


@pytest.mark.parametrize("schedule", ["ordinary", "layer_major", "multiple_outer"])
def test_original_single_request_geometry_and_d03_tail_binding(tmp_path, monkeypatch, schedule):
    f = fixture(tmp_path, monkeypatch)
    chunks = [batch(0, 5), batch(5, 10), batch(10, 12)]
    if schedule == "ordinary":
        output = f.engine.forward_batch(batch(0, 12))
        tail_batches = [(0, 12)]
        assert f.order == [(0, 0, 12), (1, 0, 12)]
        assert f.mix_shapes == [(12, 4)]
    elif schedule == "layer_major":
        output = f.engine.forward_batch(batch(0, 12), chunks)
        tail_batches = [(5, 10), (10, 12)]
        assert f.order == [(layer, start, end) for layer in (0, 1) for start, end in ((0, 5), (5, 10), (10, 12))]
        # Last child uses its actual production mix; earlier tail child is mixed
        # with all five rows, not its two selected tail rows.
        assert f.mix_shapes == [(2, 4), (5, 4)]
    else:
        for current in chunks:
            output = f.engine.forward_batch(current)
        tail_batches = [(5, 10), (10, 12)]
        assert f.order == [(layer, start, end) for start, end in ((0, 5), (5, 10), (10, 12)) for layer in (0, 1)]
        assert f.mix_shapes == [(5, 4), (5, 4), (2, 4)]
    f.capture.finish()
    row = json.loads((f.root / "index.jsonl").read_text().strip())
    logits = f.d03.reader.read_tensor(f.root, row, "logits")
    assert f.d03.reader.binding(row, logits) == (f.d03.reader.sha(list(range(12))), 4, 12, [8, 9, 10, 11])
    expected = []
    for start, end in tail_batches:
        full = f.native_mix(f.embed(torch.arange(start, end)).repeat(1, 2) + 0.375)[0]
        expected.append(full[max(start, 8)-start:end-start])
    expected_logits = f.d03.project(f.engine.model.lm_head, torch.cat(expected))
    assert torch.equal(logits, expected_logits)
    assert torch.equal(output, expected_logits[-1:])
    assert set(row["files"]) == {"logits", "conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx"}
    assert row["extra"]["restore_proof"] is None
    assert len([event for event in f.events if event["schema"] == "ft_d12_prompt_tail_logits/v1"]) == 1
    f.capture.restore()
    f.restore_segment()
    assert not torch.cuda.is_initialized()


def test_hidden_bound_rejects_before_retention(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, maximum=1)
    with pytest.raises(ValueError, match="budget"):
        f.engine.forward_batch(batch(0, 12))
    assert not (f.root / "index.jsonl").exists()
    with pytest.raises(ValueError, match="incomplete"):
        f.capture.finish()
    f.capture.restore()
    f.restore_segment()


def test_missing_tail_rows_and_changed_ownership_are_rejected(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    # Claiming a full outer input while actually omitting positions 8/9 must not
    # produce a complete D03 record.
    with pytest.raises(ValueError, match="incomplete"):
        f.engine.forward_batch(batch(0, 12), [batch(10, 12)])
    assert not (f.root / "index.jsonl").exists()
    f.capture.layer.forward = lambda hidden, batch: hidden
    with pytest.raises(RuntimeError, match="ownership"):
        f.capture.restore()
    assert f.capture.mixer.mix is f.capture.original_mix
    f.restore_segment()


@pytest.mark.parametrize("complete", [False, True])
def test_worker_installer_binds_tail_events_and_incomplete_cleanup(tmp_path, monkeypatch, complete):
    import worker_capture
    from freetoken.core import SamplingParams
    from freetoken.message.backend import UserMsg

    f = fixture(tmp_path, monkeypatch, length=80, k=64)
    f.capture.restore()
    f.restore_segment()
    capture = tmp_path / "dev_D16" / "worker"
    dump = capture / "d12_state"
    monkeypatch.setattr(linear_state_pool, "DUMP_PATH", str(dump))
    monkeypatch.setenv("FT_DEV_STATE_DUMP", str(dump))
    monkeypatch.setenv("FT_DEV_LOGITS_DUMP", str(capture / "d12_prompt_tail"))
    monkeypatch.setenv("FT_D12_PROMPT_TAIL", "1")
    monkeypatch.setenv("FT_D12_TAIL_HIDDEN_BYTES", "1000000")
    monkeypatch.setenv("FT_D12_DIAGNOSTIC", "1")
    monkeypatch.setenv("FT_D12_MAX_EVENTS", "1024")
    monkeypatch.setenv("FT_D12_MAX_EVENT_BYTES", "1000000")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(capture))
    assert worker_capture.prepare_environment() == (capture, dump, (1024, 1000000))

    class Cache:
        quant_format, prefill_overlap, prefill_routed_only_max_tokens = "nvfp4", False, 0
        def prepare_prefill_routed_only(self, *_):
            raise AssertionError("CPU model fixture does not execute MoE")
    f.engine.moe_offload_cache = Cache()
    original_forward = f.engine.forward_batch
    shutdowns, errors = [], []
    scheduler = SimpleNamespace(engine=f.engine, shutdown=lambda: shutdowns.append(1))
    adapter = SimpleNamespace(destination=capture, expected_queries=[{"uid": 0}],
        registry=SimpleNamespace(get=lambda uid: {"event_identity": "cpu-admission", "prompt_sha256": "cpu-input"}),
        capture=SimpleNamespace(process_identity={"pid": 1, "start_ticks": 2, "execution_id": "cpu-only"}),
        record_observer_error=errors.append, admit_user_msg=lambda message: None)
    close = worker_capture.install_worker_capture(scheduler, adapter, capture, dump, (1024, 1000000), f.binding)
    if complete:
        adapter.admit_user_msg(UserMsg(uid=0, input_ids=torch.arange(80, dtype=torch.int32),
                                       sampling_params=SamplingParams(max_tokens=2048, temperature=0)))
        f.engine.forward_batch(batch(0, 80), [batch(0, 24), batch(24, 64), batch(64, 80)])
    scheduler.shutdown()
    close()
    assert shutdowns == [1] and f.engine.forward_batch is original_forward
    assert bool(errors) is not complete
    if not complete:
        assert any("prompt-tail capture is incomplete" in error for error in errors)
    else:
        records = [json.loads(line) for line in (capture / "d12_events.jsonl").read_bytes().splitlines()]
        assert [row["evidence"]["schema"] for row in records] == [
            "ft_d12_post_prefill_state/v1", "ft_d12_prompt_tail_logits/v1"]
        assert all(row["physical_event_identity"] == "cpu-admission" and
                   row["frozen_input"]["bundle_sha256"] == f.binding["bundle_sha256"] for row in records)
        assert records[-1]["evidence"]["record"]["extra"]["positions"] == list(range(16, 80))
    assert not torch.cuda.is_initialized()
