from types import SimpleNamespace

import torch

from freetoken.engine.engine import Engine


def _batch():
    reqs = [SimpleNamespace(uid=101, table_idx=7, linear_slot_idx=17),
            SimpleNamespace(uid=102, table_idx=8, linear_slot_idx=18)]
    return SimpleNamespace(
        reqs=reqs, padded_reqs=reqs, is_decode=True, is_prefill=False, size=2,
        input_ids=torch.tensor([31, 32]), positions=torch.tensor([91, 92]),
        out_loc=torch.tensor([201, 202]), mrope_positions=None,
        linear_table_idx=torch.tensor([17, 18]), active_table_idx=torch.tensor([7, 8]),
        fla_metadata=None,
    )


def test_d10_is_default_off_and_requires_exact_two_cuda_lanes():
    engine = object.__new__(Engine)
    engine.config = SimpleNamespace(d10_staggered_decode=False)
    engine.device = torch.device("cuda")
    engine.moe_offload_cache = object()
    engine.model = SimpleNamespace(forward_staggered_decode=lambda *_: None)
    assert not engine._can_use_d10_staggered(_batch(), tracer=None)

    engine.config.d10_staggered_decode = True
    engine.device = torch.device("cpu")
    assert not engine._can_use_d10_staggered(_batch(), tracer=None)
    engine.device = torch.device("cuda")
    one = _batch(); one.reqs = one.reqs[:1]; one.size = 1
    assert not engine._can_use_d10_staggered(one, tracer=None)
    assert not engine._can_use_d10_staggered(_batch(), tracer=object())


def test_d10_builds_two_scalar_batches_with_isolated_lane_contract(monkeypatch):
    """CPU orchestration contract for the production Engine D10 entry.

    CUDA streams are replaced only at the prototype boundary; the test executes
    the actual Engine child-batch construction and verifies the model receives
    request-local KV/GDN addressing plus non-overlapping cache ownership.
    """
    import freetoken.moe.staggered_decode as staggered

    class Prototype:
        def __init__(self, device, *, enabled):
            assert device.type == "cpu" and enabled

    monkeypatch.setattr(staggered, "StaggeredDecodePrototype", Prototype)

    calls = []
    class Cache:
        def __init__(self, size): self.cache_size, self.reset_calls = size, 0
        def reset(self): self.reset_calls += 1
    lane_caches = (Cache(4), Cache(4))
    base_cache = Cache(8)
    monkeypatch.setattr("freetoken.moe.offload_cache.make_d10_lane_caches", lambda cache: lane_caches)

    class Attn:
        def prepare_metadata(self, child):
            child.attn_metadata = (child.reqs[0].uid, tuple(child.active_table_idx.tolist()))

    class Model:
        def forward_staggered_decode(self, lanes, prototype):
            calls.append((lanes, prototype))
            return torch.tensor([[1.0, 2.0], [3.0, 4.0]])

    engine = object.__new__(Engine)
    engine.device = torch.device("cpu")
    engine.moe_offload_cache = base_cache
    engine.linear_state_pool = None
    engine.attn_backend = Attn()
    engine.model = Model()

    result = engine._forward_d10_staggered_decode(_batch())
    lanes, prototype = calls[0]
    assert result.tolist() == [[1.0, 2.0], [3.0, 4.0]]
    assert isinstance(prototype, Prototype)
    assert [lane.name for lane in lanes] == ["req-101", "req-102"]
    assert [lane.batch.input_ids.tolist() for lane in lanes] == [[31], [32]]
    assert [lane.batch.out_loc.tolist() for lane in lanes] == [[201], [202]]
    assert [lane.state_slots for lane in lanes] == [(17,), (18,)]
    assert set(lanes[0].cache_slots).isdisjoint(lanes[1].cache_slots)
    assert [lane.moe_cache for lane in lanes] == list(lane_caches)
    assert [lane.batch.attn_metadata for lane in lanes] == [(101, (7,)), (102, (8,))]
    assert base_cache.reset_calls == 1
