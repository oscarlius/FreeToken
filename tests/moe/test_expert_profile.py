from __future__ import annotations

import importlib.util
import os
import struct
from pathlib import Path

import numpy as np
import pytest
torch = pytest.importorskip("torch")

from freetoken.moe.expert_profile import MAGIC, read_profile, rank_frequencies, write_profile


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
    boundary = cache.seal_decode_boundary(FakeEvent(True, "cpu"))
    plan = cache.plan_profile_adaptation(boundary, cache.cpu_fixture_quiescent_proof())
    assert cache.apply_profile_adaptation_for_cpu_fixture(plan, cache.cpu_fixture_quiescent_proof()).swaps == 1
    assert int(cache.slot_for_id[0, 2]) >= 8
    assert all(int(cache.id_of_slot[slot]) == -1 for slot in range(8))
    assert cache.expert_policy_stats()["swap_bytes"] == 32


class FakeEvent:
    def __init__(self, complete, device):
        self.complete, self.device = complete, device

    def query(self):
        return self.complete


def test_adaptation_indeterminate_for_unsealed_incomplete_or_foreign_event(monkeypatch, tmp_path):
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
    for event in (None, FakeEvent(False, "cpu"), FakeEvent(True, "cuda:0")):
        boundary = cache.seal_decode_boundary(event)
        assert boundary.status == "indeterminate"
        assert cache.plan_profile_adaptation(boundary).status == "indeterminate"
        assert torch.equal(cache.id_of_slot, before_slots)
    boundary = cache.seal_decode_boundary(FakeEvent(True, "cpu"))
    assert cache.plan_profile_adaptation(boundary).status == "indeterminate"
    plan = cache.plan_profile_adaptation(boundary, cache.cpu_fixture_quiescent_proof())
    assert cache.apply_profile_adaptation_for_cpu_fixture(plan, cache.cpu_fixture_quiescent_proof()).status == "verified"
    assert cache.plan_profile_adaptation(boundary, cache.cpu_fixture_quiescent_proof()).status == "indeterminate"


def test_profile_policy_requires_explicit_profile(monkeypatch):
    from freetoken.moe.offload_cache import OffloadMoeCache

    monkeypatch.setenv("FT_DEV_EXPERT_POLICY", "profile")
    monkeypatch.delenv("FT_DEV_EXPERT_PROFILE", raising=False)
    cache = OffloadMoeCache(1, 4, 6, torch.device("cpu"))
    with pytest.raises(ValueError, match="FT_DEV_EXPERT_PROFILE"):
        cache.set_bank_sources({"gate_up": [torch.zeros(4, 2)], "down": [torch.zeros(4, 2)]})
