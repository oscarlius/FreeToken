"""CPU-only contracts for schedule-frozen D0 prefill metadata."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import torch

from freetoken.moe import offload_cache
from freetoken.moe.offload_cache import OffloadMoeCache


def _cache(tmp_path, *, enabled: bool = True) -> OffloadMoeCache:
    """Minimal cache shape: these tests exercise host-only telemetry bookkeeping."""
    cache = OffloadMoeCache.__new__(OffloadMoeCache)
    cache._d0_on = enabled
    cache._d0_layers = []
    cache._d0_chunk_idx = 0
    cache._d0_h2d = 0
    cache._d0_d2d = 0
    cache._d0_t_begin = 0.0
    cache._d0_prefill_path = str(tmp_path / "d0_prefill.jsonl")
    cache._d0_decode_path = str(tmp_path / "d0_decode.json")
    cache._d0_decode_finished = False
    cache._d0_decode_lock = threading.RLock()
    cache.decode_target = "gpu"
    cache.device = torch.device("cpu")
    cache.prefill_overlap = False
    cache.anchor_snapshot_source = SimpleNamespace(anchor_snapshots_taken=0)
    cache.decode_miss_stats = lambda: {"misses": 3}
    cache.decode_miss_stats_per_layer = lambda: [{"layer": 0, "misses": 3}]
    return cache


def _complete_layer(cache: OffloadMoeCache, layer: int = 0) -> None:
    cache._d0_layers.append(
        {
            "layer": layer,
            "copy_start": None,
            "copy_end": None,
            "compute_start": None,
            "compute_end": None,
            "d2d_start": None,
            "d2d_end": None,
        }
    )


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message, *args) -> None:
        self.messages.append(message % args)


def test_segment_end_keeps_metadata_aligned_and_immutable(tmp_path, monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(offload_cache, "logger", logger)
    cache = _cache(tmp_path)
    first = SimpleNamespace(
        seg_reason="anchor_cap",
        seg_reqs=[{"rid": 7, "new_tokens": 12, "cached_tokens": 4}],
    )
    second = SimpleNamespace(
        seg_reason="token_budget",
        seg_reqs=[{"rid": 9, "new_tokens": 8, "cached_tokens": 0}],
    )

    cache._d0_begin_prefill(first)
    first.seg_reqs[0]["new_tokens"] = 999  # scheduler may mutate after admission
    _complete_layer(cache)
    cache.end_prefill()
    cache._d0_begin_prefill(second)
    _complete_layer(cache)
    cache.end_prefill()

    records = [json.loads(line) for line in (tmp_path / "d0_prefill.jsonl").read_text().splitlines()]
    assert [(r["chunk"], r["seg_reason"], r["reqs"]) for r in records] == [
        (0, "anchor_cap", [{"rid": 7, "new_tokens": 12, "cached_tokens": 4}]),
        (1, "token_budget", [{"rid": 9, "new_tokens": 8, "cached_tokens": 0}]),
    ]
    assert "D0 seg: idx=0 reason=anchor_cap reqs=7:12/4" in logger.messages
    assert "D0 seg: idx=1 reason=token_budget reqs=9:8/0" in logger.messages


def test_d0_off_writes_no_prefill_or_decode_telemetry(tmp_path, monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(offload_cache, "logger", logger)
    cache = _cache(tmp_path, enabled=False)
    cache._d0_begin_prefill(SimpleNamespace(seg_reason="anchor_cap", seg_reqs=[]))
    _complete_layer(cache)
    cache._d0_flush_chunk()
    cache._d0_finish_decode()

    assert not (tmp_path / "d0_prefill.jsonl").exists()
    assert not (tmp_path / "d0_decode.json").exists()
    assert not any(message.startswith("D0 seg:") for message in logger.messages)


def test_final_decode_snapshot_includes_successful_anchor_count_once(tmp_path, monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(offload_cache, "logger", logger)
    cache = _cache(tmp_path)
    cache.anchor_snapshot_source.anchor_snapshots_taken = 2

    cache._d0_write_decode()
    periodic = json.loads((tmp_path / "d0_decode.json").read_text())
    assert periodic["anchor_snapshots_taken"] == 2
    assert "expert_policy" not in periodic  # legacy host-only fixture has no policy counters

    cache._d0_finish_decode()
    cache.anchor_snapshot_source.anchor_snapshots_taken = 3
    cache._d0_finish_decode()

    snapshot = json.loads((tmp_path / "d0_decode.json").read_text())
    assert snapshot["anchor_snapshots_taken"] == 2
    assert snapshot["misses"] == 3
    assert logger.messages.count("D0 anchor_snapshots_taken=2") == 1
