from __future__ import annotations

import torch

from freetoken.core import Context, SamplingParams, get_global_ctx, set_global_ctx
from freetoken.scheduler.cache import CacheManager
from freetoken.scheduler.decode import DecodeManager
from freetoken.scheduler.prefill import PrefillManager
from freetoken.scheduler.prefill_trace import (
    SEG_REASON_ANCHOR_CAP,
    SEG_REASON_CONTINUATION,
    SEG_REASON_LAYER_MAJOR_WHOLE,
    SEG_REASON_OTHER,
    SEG_REASON_TOKEN_BUDGET,
)
from freetoken.scheduler.table import TableManager
from freetoken.scheduler.utils import PendingReq


def _manager(*, anchor_ids=frozenset(), anchor_cut=True, layer_major=False):
    try:
        get_global_ctx()
    except AssertionError:
        set_global_ctx(Context(page_size=1))
    table = torch.zeros((8, 64), dtype=torch.int32)
    cache = CacheManager(num_pages=64, page_size=1, page_table=table, type="radix")
    return PrefillManager(
        cache,
        TableManager(max_running_reqs=7, page_table=table),
        DecodeManager(page_size=1),
        anchor_ids=anchor_ids,
        prefill_anchor_cut=anchor_cut,
        layer_major=layer_major,
    )


def _pending(uid, ids):
    return PendingReq(uid, torch.tensor(ids, dtype=torch.int32), SamplingParams(max_tokens=1))


def test_anchor_cut_switch_only_gates_prefill_scan():
    anchored = list(range(12))
    anchored[5] = 99
    on = _manager(anchor_ids=frozenset({99}), anchor_cut=True)
    on.pending_list = [_pending(1, anchored)]
    on_batch = on.schedule_next_batch(12)
    assert on_batch.reqs[0].extend_len == 5
    assert on_batch.seg_reason == SEG_REASON_ANCHOR_CAP

    off = _manager(anchor_ids=frozenset({99}), anchor_cut=False)
    off.pending_list = [_pending(1, anchored)]
    off_batch = off.schedule_next_batch(12)
    assert off.anchor_ids == frozenset({99})
    assert off_batch.reqs[0].extend_len == 12
    assert off_batch.seg_reason == SEG_REASON_OTHER


def test_message_boundary_creates_one_exact_prefill_cut():
    manager = _manager()
    pending = _pending(1, range(60))
    pending.message_boundary_len = 50
    manager.pending_list = [pending]
    batch = manager.schedule_next_batch(55)
    assert batch.reqs[0].extend_len == 50
    assert batch.reqs[0].message_boundary_len == 50
    assert batch.seg_reason == SEG_REASON_ANCHOR_CAP


def test_message_boundary_uses_only_the_final_adjacent_literal_pair():
    from freetoken.scheduler.scheduler import d09_message_boundary

    ids = torch.zeros(22_000, dtype=torch.int32)
    ids[20_282] = ids[21_297] = 248_045
    assert d09_message_boundary(ids, 248_045) == 20_282

    ids[21_297] = 0
    ids[20_300] = 248_045  # a farther marker cannot stand in for generation header
    assert d09_message_boundary(ids, 248_045) == 20_282

    ids[20_300] = 0
    ids[21_400] = 248_045
    assert d09_message_boundary(ids, 248_045) is None  # tail 1118 > 1024
    assert d09_message_boundary(ids, None) is None


def test_anchor_mode_selects_first_or_last_without_switch_changes(monkeypatch):
    ids = list(range(12))
    ids[3] = 99
    ids[8] = 99
    for mode, expected in (("first", 3), ("last", 8)):
        monkeypatch.setenv("FT_D3_ANCHOR_MODE", mode)
        manager = _manager(anchor_ids=frozenset({99}))
        manager.pending_list = [_pending(1, ids)]
        batch = manager.schedule_next_batch(12)
        assert batch.reqs[0].extend_len == expected
        assert batch.seg_reason == SEG_REASON_ANCHOR_CAP


def test_segment_reason_tracks_actual_final_cap():
    token = _manager()
    token.pending_list = [_pending(1, range(20))]
    assert token.schedule_next_batch(8).seg_reason == SEG_REASON_TOKEN_BUDGET

    layer_major = _manager(layer_major=True)
    layer_major.pending_list = [_pending(1, range(20))]
    assert layer_major.schedule_next_batch(8).seg_reason == SEG_REASON_LAYER_MAJOR_WHOLE

    continuation = _manager()
    continuation.pending_list = [_pending(1, range(12))]
    first = continuation.schedule_next_batch(8)
    for req in first.reqs:
        continuation.cache_manager.allocate_paged([req])
        req.complete_one()
    second = continuation.schedule_next_batch(8)
    assert second.seg_reason == SEG_REASON_CONTINUATION
    assert second.seg_reqs == [{"rid": 1, "new_tokens": 4, "cached_tokens": 0}]


def test_batch_reason_uses_documented_priority_and_schedule_snapshot():
    ids = list(range(20))
    ids[5] = 99
    manager = _manager(anchor_ids=frozenset({99}))
    manager.pending_list = [_pending(1, ids), _pending(2, range(20))]
    batch = manager.schedule_next_batch(8)

    assert batch.seg_reason == SEG_REASON_ANCHOR_CAP
    assert [req.seg_reason for req in batch.reqs] == [
        SEG_REASON_ANCHOR_CAP,
        SEG_REASON_TOKEN_BUDGET,
    ]
    snapshot = [dict(item) for item in batch.seg_reqs]
    assert sum(item["new_tokens"] for item in snapshot) == batch.log_new_tokens
    assert sum(item["cached_tokens"] for item in snapshot) == batch.log_cached_tokens
    for req in batch.reqs:
        manager.cache_manager.allocate_paged([req])
        req.complete_one()
    assert batch.seg_reqs == snapshot


def test_segment_metadata_uses_cache_hit_only_on_first_segment():
    manager = _manager()
    manager.pending_list = [_pending(1, range(8))]
    first = manager.schedule_next_batch(8)
    req = first.reqs[0]
    manager.cache_manager.allocate_paged([req])
    req.complete_one()
    manager.cache_manager.cache_req(req, finished=True)
    manager.table_manager.free(req.table_idx)

    manager.pending_list = [_pending(2, range(12))]
    hit = manager.schedule_next_batch(12)
    assert hit.seg_reqs == [{"rid": 2, "new_tokens": 4, "cached_tokens": 8}]
    assert hit.log_new_tokens == 4
    assert hit.log_cached_tokens == 8
