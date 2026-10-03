"""Host-only D02 contracts: immediate final-segment publication and opt-in guards."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
import torch

from freetoken.engine.graph import GraphRunner
from freetoken.moe import offload_cache
from freetoken.moe.offload_cache import OffloadMoeCache, dev_d0_timeline_enabled


def _cache(tmp_path, enabled=True):
    cache = OffloadMoeCache.__new__(OffloadMoeCache)
    cache._d0_on = enabled
    cache.device = torch.device("cpu")
    cache._d0_chunk_idx = 0
    cache._d0_prefill_path = str(tmp_path / "d0_prefill.jsonl")
    cache.prefill_overlap = False
    return cache


def _batch():
    return SimpleNamespace(seg_reason="continuation", seg_reqs=[
        {"rid": 11, "new_tokens": 8, "cached_tokens": 0},
        {"rid": 12, "new_tokens": 4, "cached_tokens": 64},
    ])


def test_last_segment_is_present_before_next_batch_or_shutdown(tmp_path):
    cache = _cache(tmp_path)
    before = time.time()
    batch = _batch()
    cache._d0_begin_prefill(batch)
    batch.seg_reqs[0]["new_tokens"] = 999
    assert not (tmp_path / "d0_prefill.jsonl").exists()
    cache._d0_h2d, cache._d0_d2d = 128, 32
    cache.end_prefill()
    record = json.loads((tmp_path / "d0_prefill.jsonl").read_text())
    assert before <= record["t_start"] <= record["t_end"] <= time.time()
    assert record["seg_reason"] == "continuation"
    assert [r["rid"] for r in record["reqs"]] == [11, 12]
    assert sum(r["new_tokens"] for r in record["reqs"]) == 12
    assert (record["h2d_bytes"], record["d2d_bytes"]) == (128, 32)
    cache.end_prefill()
    assert len((tmp_path / "d0_prefill.jsonl").read_text().splitlines()) == 1


def test_warmup_begin_does_not_start_or_publish_a_real_segment(tmp_path):
    cache = _cache(tmp_path)
    cache.begin_prefill(_batch())
    cache.end_prefill()
    assert not list(tmp_path.iterdir())


def test_disabled_guard_creates_no_files(tmp_path):
    cache = _cache(tmp_path, enabled=False)
    cache._d0_begin_prefill(_batch())
    cache.end_prefill()
    cache._d0_begin_decode(SimpleNamespace())
    cache._d0_end_decode()
    cache._d0_decode_mark(0, "copy_start")
    assert not list(tmp_path.iterdir())


def test_new_segment_cannot_hide_an_unfinished_previous_one(tmp_path):
    cache = _cache(tmp_path)
    cache._d0_begin_prefill(_batch())
    with pytest.raises(RuntimeError, match="did not finish"):
        cache._d0_begin_prefill(_batch())


def test_prefill_write_failure_propagates_and_keeps_last_written_line(tmp_path):
    cache = _cache(tmp_path)
    cache._d0_begin_prefill(_batch())
    cache.end_prefill()
    path = tmp_path / "d0_prefill.jsonl"
    previous = path.read_bytes()
    cache._d0_begin_prefill(_batch())
    cache._d0_prefill_path = str(tmp_path / "missing-parent" / "d0_prefill.jsonl")
    with pytest.raises(FileNotFoundError):
        cache.end_prefill()
    assert path.read_bytes() == previous
    assert cache._d0_prefill_active


def test_gpu_decode_counts_use_lru_misses_as_actual_fetched_rows(tmp_path):
    cache = _cache(tmp_path)
    cache.decode_target = "gpu"
    cache.lru_stats = torch.tensor([[8, 3, 1], [7, 2, 1]], dtype=torch.int64)
    missing, fetched = cache._d0_decode_counts()
    assert missing == fetched == [3, 2]
    assert missing is not fetched


def test_hybrid_decode_counts_preserve_capped_fetch(tmp_path):
    cache = _cache(tmp_path)
    cache.decode_target = "hybrid"
    cache.stat_missing_layer = torch.tensor([5, 7])
    cache.stat_fetched_layer = torch.tensor([1, 3])
    assert cache._d0_decode_counts() == ([5, 7], [1, 3])


@pytest.mark.parametrize("d0,timeline,enabled", [(None, "1", False), ("1", None, False), ("1", "1", True)])
def test_timeline_requires_both_flags(monkeypatch, d0, timeline, enabled):
    for key, value in (("FT_DEV_D0", d0), ("FT_DEV_D0_TIMELINE", timeline)):
        monkeypatch.delenv(key, raising=False)
        if value is not None:
            monkeypatch.setenv(key, value)
    assert dev_d0_timeline_enabled() is enabled
    monkeypatch.setattr(GraphRunner, "_capture_graphs", lambda *args: None)
    runner = GraphRunner(None, None, None, None, [1, 2], 2, 0, 8, 16, None)
    assert runner.graph_bs_list == ([] if enabled else [1, 2])


def test_new_cache_attributes_have_class_defaults():
    assert OffloadMoeCache._d0_on is False
    assert OffloadMoeCache._d0_prefill_active is False
    assert OffloadMoeCache._d0_decode_recorder is None
