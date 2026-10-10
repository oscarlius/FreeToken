from __future__ import annotations

import importlib.util
import json
import os
import struct
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
torch = pytest.importorskip("torch")

from freetoken.moe.expert_profile import MAGIC, read_profile, rank_frequencies, write_profile
from freetoken.moe.adaptation_boundary import AdaptationBoundary
from freetoken.scheduler.scheduler import Scheduler


def test_strp_profile_is_strata_layout_and_round_trips(tmp_path):
    profile = rank_frequencies(2, 4, [1, 9, 2, 0, 3, 1, 7, 4])
    output = tmp_path / "profile.strp"
    write_profile(output, profile)
    raw = output.read_bytes()
    assert raw[:4] == MAGIC
    assert struct.unpack_from("<5I", raw, 4) == (1, 2, 4, 8, 8)
    restored = read_profile(output, num_layers=2, num_experts=4)
    assert (restored.num_layers, restored.num_experts, restored.ranked) == (2, 4, profile.ranked)


def test_profile_tool_consumes_d07_synthetic_trace(tmp_path):
    route_dir = tmp_path / "route"
    route_dir.mkdir()
    ids = np.array([[[1] * 10, [1] * 10], [[3] * 10, [2] * 10]], dtype=np.int16)
    np.savez_compressed(route_dir / "route-00000000.npz", expert_ids=ids)
    tool_path = Path("tools/build_expert_profile.py")
    spec = importlib.util.spec_from_file_location("d15_profile_tool", tool_path)
    tool = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(tool)
    output = tmp_path / "profile.strp"
    assert tool.build(route_dir, output, 4) == {"records": 1, "layers": 2, "experts": 4, "routes": 40}
    assert read_profile(output).ranked[:3] == ((0, 1), (1, 2), (1, 3))


def test_d07_profile_preload_adapt_and_counters_end_to_end(monkeypatch, tmp_path):
    """A D07 route artifact drives the complete CPU-only D15 policy path."""
    from freetoken.moe.offload_cache import OffloadMoeCache

    route_dir = tmp_path / "route"
    route_dir.mkdir()
    # D07's real record shape is [layer, token, top_k=10].  Experts 0 and 1
    # become the two startup residents; later decode routing promotes expert 2.
    ids = np.array([[[0] * 10, [0] * 10, [1] * 10, [2] * 10]], dtype=np.int16)
    np.savez_compressed(route_dir / "route-00000000.npz", expert_ids=ids)
    tool_path = Path("tools/build_expert_profile.py")
    spec = importlib.util.spec_from_file_location("d15_profile_tool_e2e", tool_path)
    tool = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(tool)
    profile_path = tmp_path / "profile.strp"
    assert tool.build(route_dir, profile_path, 4) == {
        "records": 1, "layers": 1, "experts": 4, "routes": 40,
    }

    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    sources = {
        "gate_up": [torch.arange(8).reshape(4, 2)],
        "down": [torch.arange(8).reshape(4, 2) + 100],
    }
    cache.set_bank_sources(sources)
    assert cache.slot_for_id.tolist() == [[8, 9, -1, -1]]
    assert torch.equal(cache.bank_caches["gate_up"][8], sources["gate_up"][0][0])
    assert torch.equal(cache.bank_caches["down"][9], sources["down"][0][1])

    cache.record_expert_policy_routes(0, torch.tensor([[0, 2, 2]], dtype=torch.int32))
    assert cache.expert_policy_stats() == {
        "policy": "profile+adapt", "state": "adapt-armed-awaiting-boundary",
        "hits": 1, "misses": 2, "hit_rate": 1 / 3, "swap_bytes": 0,
    }
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert plan.status == "verified" and plan.replacements == ((8, 0, 2),)
    assert cache.apply_profile_adaptation(plan, proof).status == "verified"
    assert cache.slot_for_id.tolist() == [[-1, 9, 8, -1]]
    assert torch.equal(cache.bank_caches["gate_up"][8], sources["gate_up"][0][2])
    assert torch.equal(cache.bank_caches["down"][8], sources["down"][0][2])
    assert cache.expert_policy_stats() == {
        "policy": "profile+adapt", "state": "adapt-boundary-proven",
        "hits": 1, "misses": 2, "hit_rate": 1 / 3, "swap_bytes": 32,
    }
    assert not cache.policy_recent.any()


def _parent_lru_cache_module():
    """Load the immutable parent implementation under an isolated module name."""
    source = subprocess.check_output(
        ["git", "show", "23f2e2c:python/freetoken/moe/offload_cache.py"],
        text=True,
    )
    name = "freetoken.moe._d15_parent_lru_reference"
    module = sys.modules.get(name)
    if module is None:
        module = type(sys)(name)
        module.__package__ = "freetoken.moe"
        sys.modules[name] = module
        exec(compile(source, "<23f2e2c-offload_cache>", "exec"), module.__dict__)
    return module


def test_default_lru_legacy_cache_tensors_match_parent_bitwise(monkeypatch):
    """Default D15 construction is byte-for-byte identical for parent LRU state."""
    from freetoken.moe.offload_cache import OffloadMoeCache

    monkeypatch.delenv("FT_DEV_EXPERT_POLICY", raising=False)
    monkeypatch.delenv("FT_DEV_EXPERT_PROFILE", raising=False)
    parent = _parent_lru_cache_module().OffloadMoeCache
    sources = {
        "gate_up": [torch.arange(8).reshape(4, 2)],
        "down": [torch.arange(8).reshape(4, 2) + 100],
    }
    current_cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    parent_cache = parent(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    current_cache.set_bank_sources(sources)
    parent_cache.set_bank_sources(sources)
    current_cache.record_expert_policy_routes(0, torch.tensor([[0, 2, 2]], dtype=torch.int32))

    for name in ("slot_for_id", "id_of_slot", "usage", "step", "active_mask", "lru_stats"):
        assert torch.equal(getattr(current_cache, name), getattr(parent_cache, name)), name
    for bank in ("gate_up", "down"):
        assert torch.equal(current_cache.bank_caches[bank], parent_cache.bank_caches[bank]), bank
    assert current_cache._adaptation_copy_stream is None


def test_profile_preload_uses_only_stable_slots_and_default_does_not(monkeypatch, tmp_path):
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [0, 10, 9, 8]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    sources = {"gate_up": [torch.arange(4 * 2).reshape(4, 2)], "down": [torch.arange(4 * 2).reshape(4, 2)]}
    cache.set_bank_sources(sources)
    assert cache.slot_for_id.tolist() == [[-1, 8, 9, -1]]
    assert torch.equal(cache.bank_caches["gate_up"][8], sources["gate_up"][0][1])
    monkeypatch.delenv("FT_DEV_EXPERT_POLICY")
    monkeypatch.delenv("FT_DEV_EXPERT_PROFILE")
    default = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    default.set_bank_sources(sources)
    assert default.id_of_slot.tolist() == [-1] * 10


def test_adaptation_stays_in_stable_slots_and_counts_copy_bytes(monkeypatch, tmp_path):
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [9, 8, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    sources = {"gate_up": [torch.arange(8).reshape(4, 2)], "down": [torch.arange(8).reshape(4, 2)]}
    cache.set_bank_sources(sources)
    cache.record_expert_policy_routes(0, torch.tensor([[2, 2]], dtype=torch.int32))
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert cache.apply_profile_adaptation(plan, proof).swaps == 1
    assert int(cache.slot_for_id[0, 2]) >= 8
    assert all(int(cache.id_of_slot[slot]) == -1 for slot in range(8))
    assert cache.expert_policy_stats()["swap_bytes"] == 32


class FakeEvent:
    def __init__(self, complete, device):
        self.complete, self.device = complete, device

    def query(self):
        return self.complete

    def synchronize(self):
        assert self.complete


class FakeStream:
    device = "cpu"

    def synchronize(self):
        return None

    def query(self):
        return True


def test_cuda_registration_requires_actual_scheduler_owner_and_exact_streams(monkeypatch, tmp_path):
    """CPU-only mechanics test: the cache is never used after its device label changes."""
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [1, 0, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 6, torch.device("cpu"))
    cache.device = torch.device("cuda:0")
    engine_stream = FakeStream()
    engine_stream.device = "cuda:0"
    scheduler_stream = FakeStream()
    scheduler_stream.device = "cuda:0"
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.engine = SimpleNamespace(moe_offload_cache=cache, stream=engine_stream)
    scheduler.stream = scheduler_stream
    boundary = AdaptationBoundary(scheduler)
    scheduler._adaptation_boundary = boundary
    streams = (engine_stream, scheduler_stream)

    assert cache._register_adaptation_boundary(
        AdaptationBoundary(scheduler), scheduler, boundary.scheduler_identity, streams, cpu_test_scope=False,
    ) is None
    assert cache._register_adaptation_boundary(
        boundary, scheduler, "scheduler:wrong", streams, cpu_test_scope=False,
    ) is None
    wrong_stream = FakeStream()
    wrong_stream.device = "cuda:0"
    assert cache._register_adaptation_boundary(
        boundary, scheduler, boundary.scheduler_identity, (engine_stream, wrong_stream), cpu_test_scope=False,
    ) is None
    coordinator = cache._register_adaptation_boundary(
        boundary, scheduler, boundary.scheduler_identity, streams, cpu_test_scope=False,
    )
    assert coordinator is not None
    assert cache._register_adaptation_boundary(
        AdaptationBoundary(scheduler), scheduler, boundary.scheduler_identity, streams, cpu_test_scope=False,
    ) is None
    assert cache._register_adaptation_boundary(
        boundary, scheduler, "scheduler:wrong", streams, cpu_test_scope=False,
    ) is None
    assert cache._register_adaptation_boundary(
        boundary, scheduler, boundary.scheduler_identity, (engine_stream, wrong_stream), cpu_test_scope=False,
    ) is None
    with pytest.raises(RuntimeError, match="CPU fixture scope"):
        cache._register_adaptation_boundary(boundary, scheduler, boundary.scheduler_identity, streams, cpu_test_scope=True)


def _issue_cpu_fixture_proof(cache, event=None, owner=None, streams=None):
    """Exercise the real coordinator through an explicit CPU-only fixture scope."""
    owner = owner or getattr(cache, "_test_boundary_owner", None)
    streams = streams or getattr(cache, "_test_boundary_streams", None)
    if owner is None:
        owner = AdaptationBoundary("cpu-fixture", cpu_test_scope=True)
        streams = (FakeStream(), FakeStream())
        cache._test_boundary_owner = owner
        cache._test_boundary_streams = streams
    coordinator = cache._register_adaptation_boundary(owner, "cpu-fixture", "cpu-fixture", streams, cpu_test_scope=True)
    assert coordinator is not None
    event = event or FakeEvent(True, "cpu")
    gate = coordinator.close_launch_gate(cache.next_adaptation_launch_generation(), event)
    assert gate is not None
    event.synchronize()
    assert coordinator.mark_last_data_drained(gate, event)
    for stream in streams:
        stream.synchronize()
    assert coordinator.mark_streams_drained(gate, streams)
    proof = coordinator.issue_proof(gate)
    assert proof is not None
    return coordinator, gate, proof, streams


def _adaptive_plan(cache):
    coordinator, gate, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert plan.status == "verified" and plan.replacements
    return plan, proof


def _volatile_slot_adaptation(monkeypatch, tmp_path):
    """Build a real policy plan whose candidate is temporarily in buffer slot 0."""
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [10, 9, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    sources = {
        "gate_up": [torch.arange(8).reshape(4, 2)],
        "down": [torch.arange(8).reshape(4, 2) + 100],
    }
    cache.set_bank_sources(sources)
    # Model the live prefill-buffer ownership that adaptation must move away from.
    cache.slot_for_id[0, 2] = 0
    cache.id_of_slot[0] = 2
    for name, source in sources.items():
        cache.bank_caches[name][0].copy_(source[0][2])
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    plan, proof = _adaptive_plan(cache)
    assert plan.replacements == ((8, 0, 2),)
    return cache, sources, plan, proof


def test_adaptation_promotion_clears_volatile_owner_before_buffer_reuse(monkeypatch, tmp_path):
    cache, sources, plan, proof = _volatile_slot_adaptation(monkeypatch, tmp_path)

    assert cache.apply_profile_adaptation(plan, proof).status == "verified"
    assert cache.slot_for_id.tolist() == [[-1, 9, 8, -1]]
    cache._invalidate_prefill_buffer(0)

    assert int(cache.slot_for_id[0, 2]) == 8
    assert int(cache.id_of_slot[0]) == -1
    for name, source in sources.items():
        assert torch.equal(cache.bank_caches[name][8], source[0][2])


def test_adaptation_volatile_promotion_copy_failure_restores_bidirectional_maps(monkeypatch, tmp_path):
    cache, _, plan, proof = _volatile_slot_adaptation(monkeypatch, tmp_path)
    old_slots, old_owners = cache.slot_for_id.clone(), cache.id_of_slot.clone()
    original_copy = torch.Tensor.copy_
    calls = {"n": 0}

    def fail_second_copy(target, source, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("copy failed")
        return original_copy(target, source, *args, **kwargs)

    monkeypatch.setattr(torch.Tensor, "copy_", fail_second_copy)
    assert cache.apply_profile_adaptation(plan, proof).status == "rolled_back"
    assert torch.equal(cache.slot_for_id, old_slots)
    assert torch.equal(cache.id_of_slot, old_owners)


@pytest.mark.parametrize("failure", ["promoted_owner_mismatch", "after_publication"])
def test_adaptation_map_publication_failure_restores_all_state(monkeypatch, tmp_path, failure):
    cache, _, plan, proof = _volatile_slot_adaptation(monkeypatch, tmp_path)
    if failure == "promoted_owner_mismatch":
        # The stable victim remains consistent; its forward map is cleared before
        # the promoted expert's bad reverse owner is detected.
        cache.id_of_slot[0] = 3
    tensors = [
        cache.slot_for_id, cache.id_of_slot, cache.usage,
        cache.policy_recent, cache.policy_swap_bytes, *cache.bank_caches.values(),
    ]
    snapshots = [tensor.clone() for tensor in tensors]
    if failure == "after_publication":
        original_zero = torch.Tensor.zero_

        def fail_after_maps(target, *args, **kwargs):
            if target is cache.policy_recent:
                raise RuntimeError("injected failure after map publication")
            return original_zero(target, *args, **kwargs)

        monkeypatch.setattr(torch.Tensor, "zero_", fail_after_maps)

    assert cache.apply_profile_adaptation(plan, proof).status == "rolled_back"
    assert all(torch.equal(tensor, snapshot) for tensor, snapshot in zip(tensors, snapshots))


def test_runtime_coordinator_constructor_issues_bound_proof(monkeypatch, tmp_path):
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [9, 8, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    cache.set_bank_sources({"gate_up": [torch.arange(8).reshape(4, 2)], "down": [torch.arange(8).reshape(4, 2)]})
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    plan, proof = _adaptive_plan(cache)
    assert proof.cache_identity == id(cache)
    assert proof.mapping_generation == plan.mapping_generation == cache._mapping_generation
    assert proof.scheduler_identity == "cpu-fixture"
    assert not hasattr(cache, "runtime_adaptation_coordinator")


def test_transaction_copy_failure_rolls_back_then_locks_when_rollback_fails(monkeypatch, tmp_path):
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [9, 8, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    cache.set_bank_sources({"gate_up": [torch.arange(8).reshape(4, 2)], "down": [torch.arange(8).reshape(4, 2)]})
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    plan, proof = _adaptive_plan(cache)
    old_slots = cache.id_of_slot.clone()
    original_copy = torch.Tensor.copy_
    calls = {"n": 0}

    def fail_once(target, source, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("copy failed")
        return original_copy(target, source, *args, **kwargs)

    monkeypatch.setattr(torch.Tensor, "copy_", fail_once)
    assert cache.apply_profile_adaptation(plan, proof).status == "rolled_back"
    assert torch.equal(cache.id_of_slot, old_slots)

    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    plan, proof = _adaptive_plan(cache)
    monkeypatch.setattr(torch.Tensor, "copy_", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("copy failed")))
    assert cache.apply_profile_adaptation(plan, proof).status == "locked"
    assert cache._register_adaptation_boundary(
        AdaptationBoundary("cpu-fixture", cpu_test_scope=True), "cpu-fixture", "cpu-fixture", (FakeStream(), FakeStream()), cpu_test_scope=True,
    ) is None


def test_adaptation_rejects_incomplete_or_stale_coordinator_proofs(monkeypatch, tmp_path):
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [1, 0, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    cache = OffloadMoeCache(1, 4, 6, torch.device("cpu"))
    cache.set_bank_sources({"gate_up": [torch.zeros(4, 2)], "down": [torch.zeros(4, 2)]})
    before_slots = cache.id_of_slot.clone()
    owner = AdaptationBoundary("cpu-fixture", cpu_test_scope=True)
    streams = (FakeStream(), FakeStream())
    coordinator = cache._register_adaptation_boundary(owner, "cpu-fixture", "cpu-fixture", streams, cpu_test_scope=True)
    assert coordinator is not None
    incomplete = FakeEvent(False, "cpu")
    gate = coordinator.close_launch_gate(cache.next_adaptation_launch_generation(), incomplete)
    assert gate is not None
    assert not coordinator.mark_last_data_drained(gate, incomplete)
    assert coordinator.issue_proof(gate) is None
    coordinator.abort_gate(gate)
    foreign = FakeEvent(True, "cuda:0")
    gate = coordinator.close_launch_gate(cache.next_adaptation_launch_generation(), foreign)
    assert gate is not None
    foreign.synchronize()
    assert coordinator.mark_last_data_drained(gate, foreign)
    for stream in streams:
        stream.synchronize()
    assert coordinator.mark_streams_drained(gate, streams)
    assert coordinator.issue_proof(gate) is None
    coordinator.abort_gate(gate)
    assert cache.plan_profile_adaptation(None).status == "indeterminate"
    assert torch.equal(cache.id_of_slot, before_slots)
    coordinator, gate, proof, _ = _issue_cpu_fixture_proof(cache, owner=owner, streams=streams)
    assert coordinator.issue_proof(gate) is None
    plan = cache.plan_profile_adaptation(proof)
    cache.ensure_experts = lambda *args: None  # mapping epoch must invalidate a stale plan
    cache._mapping_generation += 1
    assert cache.apply_profile_adaptation(plan, proof).status == "indeterminate"


def test_profile_policy_requires_explicit_profile(monkeypatch):
    from freetoken.moe.offload_cache import OffloadMoeCache

    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile")
    monkeypatch.delenv("FT_DEV_EXPERT_PROFILE", raising=False)
    cache = OffloadMoeCache(1, 4, 6, torch.device("cpu"))
    with pytest.raises(ValueError, match="FT_DEV_EXPERT_PROFILE"):
        cache.set_bank_sources({"gate_up": [torch.zeros(4, 2)], "down": [torch.zeros(4, 2)]})


def _lag1_cache(monkeypatch, tmp_path):
    from freetoken.moe.offload_cache import OffloadMoeCache

    profile_path = tmp_path / "profile.strp"
    write_profile(profile_path, rank_frequencies(1, 4, [10, 9, 0, 0]))
    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile+adapt")
    monkeypatch.setenv("FT_DEV_EXPERT_PROFILE", os.fspath(profile_path))
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_EVERY", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_SWAPS", "1")
    monkeypatch.setenv("FT_DEV_EXPERT_ADAPT_LAG1", "1")
    cache = OffloadMoeCache(1, 4, 10, torch.device("cpu"), prefill_overlap=True)
    sources = {
        "gate_up": [torch.arange(8).reshape(4, 2)],
        "down": [torch.arange(8).reshape(4, 2) + 100],
    }
    cache.set_bank_sources(sources)
    return cache, sources


def test_lag1_stages_aux_copy_and_publishes_only_at_a_later_completed_boundary(monkeypatch, tmp_path):
    cache, sources = _lag1_cache(monkeypatch, tmp_path)
    # Expert 1 occupies stable slot 9.  Both requests use it in the current
    # top-k, so the actual replacement must use slot 8 instead.
    cache.record_expert_policy_routes(0, torch.tensor([[1, 2], [1, 2]], dtype=torch.int32))
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert plan.replacements == ((8, 0, 2),)
    old_slots, old_owners = cache.slot_for_id.clone(), cache.id_of_slot.clone()
    old_rows = {name: bank[8].clone() for name, bank in cache.bank_caches.items()}
    event = FakeEvent(False, "cpu")
    assert cache.enqueue_profile_adaptation(plan, proof, event_factory=lambda: event).status == "enqueued"
    assert torch.equal(cache.slot_for_id, old_slots)
    assert torch.equal(cache.id_of_slot, old_owners)
    assert all(torch.equal(cache.bank_caches[name][8], row) for name, row in old_rows.items())
    _, _, next_proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.publish_pending_adaptation(next_proof).status == "pending"
    assert torch.equal(cache.slot_for_id, old_slots)
    event.complete = True
    _, _, publish_proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.publish_pending_adaptation(publish_proof).status == "verified"
    assert cache.slot_for_id.tolist() == [[-1, 9, 8, -1]]
    assert cache.id_of_slot[:8].tolist() == [-1] * 8  # volatile [0, 2E) remains untouched
    assert torch.equal(cache.bank_caches["gate_up"][8], sources["gate_up"][0][2])


def test_lag1_publish_failure_restores_real_maps_after_partial_staged_copy(monkeypatch, tmp_path):
    cache, _ = _lag1_cache(monkeypatch, tmp_path)
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert cache.enqueue_profile_adaptation(plan, proof).status == "enqueued"
    old_slots, old_owners = cache.slot_for_id.clone(), cache.id_of_slot.clone()
    old_rows = [bank.clone() for bank in cache.bank_caches.values()]
    original_copy = torch.Tensor.copy_
    calls = {"n": 0}

    def fail_second_publish(target, source, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("injected publish failure")
        return original_copy(target, source, *args, **kwargs)

    monkeypatch.setattr(torch.Tensor, "copy_", fail_second_publish)
    _, _, next_proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.publish_pending_adaptation(next_proof).status == "rolled_back"
    assert cache._pending_adaptation is None
    assert torch.equal(cache.slot_for_id, old_slots)
    assert torch.equal(cache.id_of_slot, old_owners)
    assert all(torch.equal(bank, old) for bank, old in zip(cache.bank_caches.values(), old_rows))


def test_lag1_invalid_map_at_publish_keeps_the_prepublication_state(monkeypatch, tmp_path):
    cache, _ = _lag1_cache(monkeypatch, tmp_path)
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert cache.enqueue_profile_adaptation(plan, proof).status == "enqueued"
    cache.id_of_slot[8] = 3  # corrupt the old victim reverse map after staging
    snapshots = [cache.slot_for_id.clone(), cache.id_of_slot.clone(), *(bank.clone() for bank in cache.bank_caches.values())]
    _, _, next_proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.publish_pending_adaptation(next_proof).status == "rolled_back"
    current = [cache.slot_for_id, cache.id_of_slot, *cache.bank_caches.values()]
    assert all(torch.equal(value, snapshot) for value, snapshot in zip(current, snapshots))


def test_lag1_d0_receipt_separates_enqueue_completion_and_publication(monkeypatch, tmp_path):
    monkeypatch.setenv("FT_DEV_D0", "1")
    monkeypatch.setenv("FT_DEV_D0_PATH", os.fspath(tmp_path / "d0"))
    cache, _ = _lag1_cache(monkeypatch, tmp_path)
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.enqueue_profile_adaptation(cache.plan_profile_adaptation(proof), proof).status == "enqueued"
    receipts = [json.loads(line) for line in (tmp_path / "d0_adaptation.jsonl").read_text().splitlines()]
    assert receipts
    pending = receipts[-1]
    assert pending["status"] == "pending"
    assert {key: pending[key] for key in ("step", "boundary_seq", "layer", "expert", "slot", "bytes")} == {
        "step": 0, "boundary_seq": 1, "layer": 0, "expert": 2, "slot": 8, "bytes": 32,
    }
    assert pending["copy_enqueue_started_at"] <= pending["copy_enqueue_finished_at"]
    assert pending["copy_completion_observed_at"] is None and pending["published_at"] is None
    assert pending["cuda_copy_elapsed_ms"] is None
    _, _, next_proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.publish_pending_adaptation(next_proof).status == "verified"
    published = [json.loads(line) for line in (tmp_path / "d0_adaptation.jsonl").read_text().splitlines()][-1]
    assert published["status"] == "published"
    assert {key: published[key] for key in ("step", "boundary_seq", "layer", "expert", "slot", "bytes")} == {
        "step": 0, "boundary_seq": 1, "layer": 0, "expert": 2, "slot": 8, "bytes": 32,
    }
    assert published["copy_completion_observed_at"] is not None
    assert published["published_at"] >= published["copy_completion_observed_at"]


def test_lag1_discards_staging_when_next_step_topk_uses_its_victim(monkeypatch, tmp_path):
    cache, _ = _lag1_cache(monkeypatch, tmp_path)
    cache.record_expert_policy_routes(0, torch.tensor([[2]], dtype=torch.int32))
    _, _, proof, _ = _issue_cpu_fixture_proof(cache)
    plan = cache.plan_profile_adaptation(proof)
    assert plan.replacements == ((8, 0, 2),)
    assert cache.enqueue_profile_adaptation(plan, proof).status == "enqueued"
    # The following decode step routes expert 0, whose old mapping owns victim 8.
    cache.record_expert_policy_routes(0, torch.tensor([[0]], dtype=torch.int32))
    before = [cache.slot_for_id.clone(), cache.id_of_slot.clone(), *(bank.clone() for bank in cache.bank_caches.values())]
    _, _, next_proof, _ = _issue_cpu_fixture_proof(cache)
    assert cache.publish_pending_adaptation(next_proof).status == "discarded"
    assert cache._pending_adaptation is None
    assert all(torch.equal(value, snapshot) for value, snapshot in zip([cache.slot_for_id, cache.id_of_slot, *cache.bank_caches.values()], before))
