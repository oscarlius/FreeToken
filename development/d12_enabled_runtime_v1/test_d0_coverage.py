"""Native D0 writer and MoE branch on controlled CPU tensors/events, not CUDA."""
import copy
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires the pinned native Linux candidate", allow_module_level=True)

import torch
from freetoken.core import Batch
from freetoken.engine.graph import GraphRunner
from freetoken.layers.moe import OffloadMoELayer
from freetoken.moe.offload_cache import OffloadMoeCache

from d0_coverage import read_coverage
import segment_capture
from test_segment_capture import Pool
from test_transfer_audit import fixture_cache
from transfer_audit import verify_routed_banks


def native_fixture(tmp_path, monkeypatch, *, mode="layer_major", threshold=256, fallback=False, tokens=600,
                   duplicate_d0=False):
    root = tmp_path / "capture"
    root.mkdir(parents=True)
    dump = root / "d12_state"
    path = root / "d12_d0_prefill.jsonl"
    monkeypatch.setattr(segment_capture, "_configured_dump_path", lambda: str(dump))
    protocol, _, _ = fixture_cache()
    cache = OffloadMoeCache.__new__(OffloadMoeCache)
    cache.__dict__.update(protocol.__dict__)
    cache.device = torch.device("cpu")
    cache.prefill_overlap, cache.prefill_routed_only_max_tokens = False, threshold
    cache._d0_on, cache._d0_prefill_active, cache._d0_chunk_idx = True, False, 0
    cache._d0_prefill_path = str(path)
    cache.prefill_routed_only_stats = None
    cache.materialize_layer = lambda layer: None
    cache.copy_missing = lambda: None
    cache.bank_views = lambda *args: tuple(value for _, value in cache.banks)
    cache.alphas_for_layer = lambda layer: None
    cache.num_indices = torch.tensor([2], dtype=torch.int64)

    class Event:
        def record(self, stream): pass
        def elapsed_time(self, other): return 0.125
    monkeypatch.setattr(torch.cuda, "Event", lambda **kwargs: Event())
    monkeypatch.setattr(torch.cuda, "current_stream", lambda *args: None)
    engine = SimpleNamespace(moe_offload_cache=cache, ctx=SimpleNamespace(batch=None), linear_state_pool=Pool(dump))
    events, calls, provider_holder = [], [], {}

    def prepare(layer, ids):
        context = provider_holder["get"]()
        if fallback:
            events.append({"schema": "ft_d12_routed_bank_fallback/v1", "layer_id": layer,
                           "context": context, "reason": "controlled_cpu_fallback", "equality_verified": False})
            return "controlled_cpu_fallback"
        raw = ids.clone()
        cache._d0_sync_prefill_mark(layer, "copy_start")
        cache.slot_for_id.fill_(-1)
        cache.id_of_slot.fill_(-1)
        for expert, slot in ((1, 4), (3, 0)):
            cache.slot_for_id[layer, expert] = slot
            cache.id_of_slot[slot] = layer * cache.num_experts + expert
            for host, resident in cache.banks: resident[slot].copy_(host[layer][expert])
        ids.copy_(cache.slot_for_id[layer][raw.long()])
        cache._d0_sync_prefill_mark(layer, "copy_end")
        evidence = verify_routed_banks(cache, layer, raw, ids)
        events.append({**evidence, "context": context})
        return None
    cache.prepare_prefill_routed_only = prepare
    layers = []
    for layer in range(2):
        moe = OffloadMoELayer.__new__(OffloadMoELayer)
        moe.offload_cache, moe.layer_id, moe.num_experts = cache, layer, 4
        moe._expert_gemm = lambda cache, hidden, *args, **kwargs: hidden
        layers.append(moe)
    lengths = [300, 256, 44] if mode == "layer_major" else [tokens]

    def forward(outer):
        cache._d0_begin_prefill(outer)
        # Native Engine._forward_layer_major publishes the builder's actual
        # lengths into this field. The CPU seam supplies this known test grid.
        cache._d0_segment["subchunks"] = lengths
        for layer in layers:
            start = outer.reqs[0].cached_len
            for n in lengths:
                child = SimpleNamespace(is_prefill=True, reqs=[SimpleNamespace(uid=0, cached_len=start, device_len=start+n)])
                engine.ctx.batch = child
                hidden = torch.ones(n, 4)
                ids = torch.tensor([[1, 3]], dtype=torch.int32).repeat(n, 1)
                result = layer._prefill_routed(hidden, torch.full((n, 2), 0.5), ids)
                assert result is hidden
                calls.append((layer.layer_id, start, start+n))
                start += n
        cache.end_prefill()
        if duplicate_d0: path.write_bytes(path.read_bytes() * 2)
        return "original-result"
    engine.forward_batch = forward
    provider, restore = segment_capture.install_prefill_segment_capture(
        SimpleNamespace(engine=engine), dump, events.append, allowed_uids=(0,), d0_path=path)
    provider_holder["get"] = provider
    outer = SimpleNamespace(is_prefill=True, is_decode=False, layer_major=mode == "layer_major",
        reqs=[SimpleNamespace(uid=0, cached_len=100, device_len=100+sum(lengths), linear_slot_idx=0)],
        # Continuation accounting is zero; absolute geometry still begins at 100.
        seg_reqs=[{"rid": 0, "new_tokens": sum(lengths), "cached_tokens": 0}])
    return SimpleNamespace(root=root, path=path, engine=engine, events=events, calls=calls, outer=outer,
                           restore=restore, threshold=threshold)


def read(fixture, *, states=None, banks=None, **overrides):
    states = [e for e in fixture.events if e["schema"] == "ft_d12_post_prefill_state/v1"] if states is None else states
    banks = [e for e in fixture.events if e["schema"] != "ft_d12_post_prefill_state/v1"] if banks is None else banks
    args = {"read_file": lambda name: (fixture.root / name).read_bytes(), "expected_layer_ids": [0, 1],
            "expected_threshold": fixture.threshold, "candidate_root": os.environ["FT_D12_NATIVE_SOURCE"], **overrides}
    return read_coverage(states, banks, **args)


@pytest.mark.parametrize("mode,threshold,tokens,calls,eligible", [
    ("ordinary", 0, 64, 2, 0), ("ordinary", 256, 64, 2, 2), ("ordinary", 256, 600, 2, 0),
    ("layer_major", 0, 600, 6, 0), ("layer_major", 256, 600, 6, 4)])
def test_native_call_denominator_and_every_eligible_bank_event(tmp_path, monkeypatch, mode, threshold, tokens, calls, eligible):
    f = native_fixture(tmp_path, monkeypatch, mode=mode, threshold=threshold, tokens=tokens)
    assert f.engine.forward_batch(f.outer) == "original-result"
    result = read(f)
    assert result["d0_protocol_verified"] and result["completed_moe_calls"] == calls
    assert result["eligible_bank_calls"] == result["routed_bank_successes"] == eligible
    assert result["routed_bank_fallbacks"] == []
    assert not result["prefill_schedule_verified"] and not result["bank_coverage_verified"]
    assert not result["routed_bank_bytes_verified"] and not result["performance_eligible"]
    assert not torch.cuda.is_initialized()
    (f.root / "d0_reader_result.json").write_text(json.dumps(result, indent=2))
    f.restore()


def test_fallbacks_are_counted_as_calls_without_claiming_bank_equality(tmp_path, monkeypatch):
    f = native_fixture(tmp_path, monkeypatch, fallback=True)
    f.engine.forward_batch(f.outer)
    result = read(f)
    assert result["eligible_bank_calls"] == 4 and len(result["routed_bank_fallbacks"]) == 4
    assert result["routed_bank_successes"] == 0 and not result["routed_path_exercised"]
    assert not result["routed_bank_bytes_verified"]
    f.restore()


@pytest.mark.parametrize("scope_case", ["fallback", "no_eligible", "all_equal", "mixed"])
def test_synthetic_cuda_scope_does_not_promote_fallback_or_empty_bank_evidence(tmp_path, monkeypatch, scope_case):
    # Mutate a CPU fixture's reader input only. This tests flag logic, never CUDA
    # execution/residency; these synthetic results are not GPU acceptance evidence.
    f = native_fixture(tmp_path, monkeypatch, threshold=0 if scope_case == "no_eligible" else 256,
                       fallback=scope_case == "fallback")
    f.engine.forward_batch(f.outer)
    states, banks = copy.deepcopy([f.events[-1]]), copy.deepcopy(f.events[:-1])
    states[0]["native_d0"]["device_type"] = "cuda"
    for row in banks:
        if row["schema"] == "ft_d12_routed_bank_equality/v1": row["scope"] = "cuda_resident_rows"
    if scope_case == "mixed":
        banks[0] = {"schema": "ft_d12_routed_bank_fallback/v1", "context": banks[0]["context"],
                    "layer_id": banks[0]["layer_id"], "reason": "synthetic_fallback", "equality_verified": False}
    result = read(f, states=states, banks=banks)
    assert result["eligible_bank_call_events_complete"]
    assert result["bank_coverage_verified"] is (scope_case == "all_equal")
    assert result["routed_bank_bytes_verified"] is (scope_case == "all_equal")
    assert not torch.cuda.is_initialized()
    f.restore()


@pytest.mark.parametrize("fault", ["layers", "threshold", "source", "offset", "sha", "extra_bytes", "partition",
    "layer_missing", "layer_order", "time", "bank_missing", "bank_order", "bank_layer", "bank_scope",
    "bank_roles", "bank_bytes", "bank_digest"])
def test_coverage_rejects_missing_or_inconsistent_evidence(tmp_path, monkeypatch, fault):
    f = native_fixture(tmp_path, monkeypatch)
    f.engine.forward_batch(f.outer)
    states = copy.deepcopy([f.events[-1]])
    banks = copy.deepcopy(f.events[:-1])
    bound = states[0]["native_d0"]
    record = bound["record"]
    overrides = {}
    if fault == "layers": overrides["expected_layer_ids"] = [0]
    elif fault == "threshold": overrides["expected_threshold"] = 0
    elif fault == "source": overrides["candidate_root"] = tmp_path
    elif fault == "offset": bound["byte_offset"] += 1
    elif fault == "sha": bound["sha256"] = "0" * 64
    elif fault == "extra_bytes": f.path.write_bytes(f.path.read_bytes() + b"\n")
    elif fault == "partition": record["subchunks"][-1] += 1
    elif fault == "layer_missing": record["layers"].pop()
    elif fault == "layer_order": record["layers"].reverse()
    elif fault == "time": record["layers"][0]["compute_ms"] = None
    elif fault == "bank_missing": banks.pop()
    elif fault == "bank_order": banks.reverse()
    elif fault == "bank_layer": banks[0]["layer_id"] = 1
    elif fault == "bank_scope": banks[0]["scope"] = "cuda_resident_rows"
    elif fault == "bank_roles": banks[0]["banks"].pop()
    elif fault == "bank_bytes": banks[0]["banks"][0]["compared_bytes"] -= 1
    elif fault == "bank_digest": banks[0]["banks"][0]["resident_sha256"] = "0" * 64
    if fault in ("partition", "layer_missing", "layer_order", "time"):
        raw = (json.dumps(record) + "\n").encode()
        f.path.write_bytes(raw)
        bound["bytes"], bound["sha256"] = len(raw), hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError): read(f, states=states, banks=banks, **overrides)
    f.restore()


def test_duplicate_native_d0_append_fails_before_state_publication(tmp_path, monkeypatch):
    f = native_fixture(tmp_path, monkeypatch, duplicate_d0=True)
    with pytest.raises(ValueError, match="exactly one"):
        f.engine.forward_batch(f.outer)
    assert not any(e["schema"] == "ft_d12_post_prefill_state/v1" for e in f.events)
    f.restore()


def test_candidate_prefill_is_eager_without_changing_decode_graphs():
    batch = Batch.__new__(Batch)
    batch.phase, batch.reqs = "prefill", [None]
    assert batch.is_prefill and not batch.is_decode
    assert not GraphRunner.can_use_cuda_graph(SimpleNamespace(max_graph_bs=100), batch)
