from __future__ import annotations

import importlib.util
import os
import struct
from pathlib import Path

import numpy as np
import pytest
torch = pytest.importorskip("torch")

from freetoken.moe.expert_profile import MAGIC, read_profile, rank_frequencies, write_profile
from freetoken.moe.adaptation_boundary import AdaptationBoundary


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


def _issue_cpu_fixture_proof(cache, event=None, owner=None, streams=None):
    """Exercise the real coordinator through an explicit CPU-only fixture scope."""
    owner = owner or getattr(cache, "_test_boundary_owner", None)
    streams = streams or getattr(cache, "_test_boundary_streams", None)
    if owner is None:
        owner = AdaptationBoundary("cpu-fixture", cpu_test_scope=True)
        streams = (FakeStream(), FakeStream())
        cache._test_boundary_owner = owner
        cache._test_boundary_streams = streams
    coordinator = cache._register_adaptation_boundary(owner, "cpu-fixture", streams, cpu_test_scope=True)
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
        AdaptationBoundary("cpu-fixture", cpu_test_scope=True), "cpu-fixture", (FakeStream(), FakeStream()), cpu_test_scope=True,
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
    coordinator = cache._register_adaptation_boundary(owner, "cpu-fixture", streams, cpu_test_scope=True)
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
