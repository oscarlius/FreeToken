"""P2b integration: CacheManager hybrid path (match_req -> cache_req donate -> prefix hit).
CPU, real LinearStatePool + page_table, hand-built Reqs. Exercises the two-currency wiring
without the full scheduler/engine."""
from __future__ import annotations

from types import SimpleNamespace

import torch
import pytest

from freetoken.core import MessageBoundaryCarrier, Req, SamplingParams
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
from freetoken.scheduler.cache import CacheManager
from freetoken.utils import div_ceil


def _pool(num_slots=16, host_slots=0):
    g = LinearGatedDeltaGroupConfig(
        name="linear", layer_ids=(0,), num_key_heads=2, num_value_heads=4,
        key_head_dim=16, value_head_dim=16, conv_kernel_dim=4, output_gate="silu",
    )
    return LinearStatePool(group=g, num_slots=num_slots, dtype=torch.bfloat16,
                           device=torch.device("cpu"), tp_size=1, host_slots=host_slots)


class _KVPool:
    """CPU stand-in for physical KV COW; values expose page aliases in scheduler tests."""

    def __init__(self, num_tokens):
        self.values = torch.arange(num_tokens, dtype=torch.int64)

    def copy_slots(self, src, dst):
        self.values[dst.long()] = self.values[src.long()]


def _pend(ids):
    # int32 to match production Req.input_ids dtype (fast_compare_key needs consistent dtype)
    t = torch.tensor(ids, dtype=torch.int32)
    return SimpleNamespace(input_ids=t, input_len=len(ids))


def test_decode_anchor_snapshot_counts_only_successful_copies(monkeypatch):
    pool = _pool()
    cm = CacheManager(64, 1, torch.zeros(4, 64, dtype=torch.int32),
                      "hybrid_radix", linear_state_pool=pool)
    req = Req(input_ids=torch.tensor([1, 2, 3, 4], dtype=torch.int32),
              table_idx=0, cached_len=3, output_len=2, uid=17,
              sampling_params=SamplingParams(), cache_handle=None)
    req.linear_slot_idx = pool.alloc(1)[0]
    req.mamba_ping_pong = tuple(pool.alloc(2))
    req.toolcall_anchor_len = 3
    pool.recurrent_states[:, req.linear_slot_idx].fill_(7)
    assert cm.anchor_snapshots_taken == 0

    cm.snapshot_toolcall_anchor([req])
    assert cm.anchor_snapshots_taken == 1
    assert req.mamba_last_track_seqlen == 3
    assert req.mamba_next_track_idx == 1
    assert torch.equal(pool.recurrent_states[:, req.linear_slot_idx],
                       pool.recurrent_states[:, req.mamba_ping_pong[0]])
    cm.snapshot_toolcall_anchor([req])
    assert cm.anchor_snapshots_taken == 1

    req.mamba_last_track_seqlen = None
    req.toolcall_anchor_len = None
    cm.snapshot_toolcall_anchor([req])
    assert cm.anchor_snapshots_taken == 1
    req.toolcall_anchor_len = 3

    def failed_copy(*args):
        raise RuntimeError("copy failed")

    monkeypatch.setattr(pool, "copy_from", failed_copy)
    with pytest.raises(RuntimeError, match="copy failed"):
        cm.snapshot_toolcall_anchor([req])
    assert cm.anchor_snapshots_taken == 1
    assert req.mamba_last_track_seqlen is None
    assert req.mamba_next_track_idx == 1


def test_decode_anchor_snapshot_counter_is_per_manager():
    cm = CacheManager(8, 1, torch.zeros(1, 8, dtype=torch.int32), "naive")
    cm.anchor_snapshots_taken = 9
    other = CacheManager(8, 1, torch.zeros(1, 8, dtype=torch.int32), "naive")
    other.snapshot_toolcall_anchor([])
    assert other.anchor_snapshots_taken == 0
    assert cm.anchor_snapshots_taken == 9


def test_message_boundary_snapshot_donates_one_existing_ping_pong_slot():
    pool = _pool()
    pt = torch.zeros(4, 64, dtype=torch.int32)
    cm = CacheManager(64, 1, pt, "hybrid_radix", linear_state_pool=pool)
    mr = cm.match_req(_pend([1, 2, 3, 4, 5, 6]))
    live, pp = pool.alloc(1)[0], tuple(pool.alloc(2))
    req = Req(input_ids=torch.tensor([1, 2, 3, 4, 5, 6], dtype=torch.int32), table_idx=0,
              cached_len=4, output_len=1, uid=9, sampling_params=SamplingParams(),
              cache_handle=mr.cuda_handle)
    req.linear_slot_idx, req.mamba_ping_pong = live, pp
    req.message_boundary_len = 4
    req.message_boundary_carrier = MessageBoundaryCarrier(boundary_len=4)
    pt[0, :4] = torch.tensor([10, 11, 12, 13], dtype=torch.int32)
    pool.recurrent_states[:, live].fill_(4)
    cm.lock(mr.cuda_handle)

    assert cm.snapshot_message_boundary(req)
    assert req.message_boundary_snapshot_len == 4
    assert req.message_boundary_snapshot_idx == 0
    assert torch.equal(pool.recurrent_states[:, live], pool.recurrent_states[:, pp[0]])
    assert not cm.snapshot_message_boundary(req)

    req.cached_len = 6
    pt[0, 4:6] = torch.tensor([14, 15], dtype=torch.int32)
    pool.recurrent_states[:, live].fill_(6)
    cm.cache_req(req, finished=True)
    hit = cm.match_req(_pend([1, 2, 3, 4, 99]))
    assert hit.cuda_handle.cached_len == 4 and hit.mamba_value == pp[0]
    restored = pool.alloc(1)[0]
    pool.copy_from(hit.mamba_value, restored)
    assert pool.recurrent_states[:, restored].unique().tolist() == [4.0]


@pytest.mark.parametrize("boundary", [20_282, 22_558])
def test_message_boundary_non_aligned_page64_keeps_exact_kv_and_state(boundary):
    """The sealed D09 boundaries are 58/62 modulo 64 and cannot be floored."""
    final = boundary + 13
    pool = _pool(num_slots=16)
    pt = torch.zeros(2, 23_104, dtype=torch.int32)
    kv = _KVPool(361 * 64)
    cm = CacheManager(361, 64, pt, "hybrid_radix", linear_state_pool=pool, kv_pool=kv)
    ids = torch.arange(final, dtype=torch.int32)
    mr = cm.match_req(_pend(ids.tolist()))
    live, pp = pool.alloc(1)[0], tuple(pool.alloc(2))
    carrier = MessageBoundaryCarrier(boundary_len=boundary)
    req = Req(input_ids=ids, table_idx=0, cached_len=0, output_len=1, uid=19,
              sampling_params=SamplingParams(), cache_handle=mr.cuda_handle)
    req.linear_slot_idx, req.mamba_ping_pong = live, pp
    req.message_boundary_len, req.message_boundary_carrier = boundary, carrier
    req.device_len = final
    cm.allocate_paged([req])
    req.cached_len = boundary
    pool.recurrent_states[:, live].fill_(boundary)
    cm.lock(mr.cuda_handle)
    assert cm.snapshot_message_boundary(req)
    req.cached_len = final
    cm.cache_req(req, finished=True)

    hit = cm.match_req(_pend(list(range(boundary + 1))))
    assert hit.cuda_handle.cached_len == boundary
    assert hit.mamba_value == pp[0]
    assert hit.cuda_handle.get_matched_indices().numel() == boundary
    assert cm._d09_entry is not None and cm._d09_entry.indices.numel() == div_ceil(boundary, 64) * 64
    restored = pool.alloc(1)[0]
    pool.copy_from(hit.mamba_value, restored)
    assert pool.recurrent_states[:, restored].unique().tolist() == [float(boundary)]
    pool.free([restored])
    cm.check_integrity()


@pytest.mark.parametrize("boundary", [20_282, 22_558])
def test_message_boundary_page64_hit_cows_partial_page_for_two_tail_lanes(boundary):
    """A second exact hit must privately own the final partial page before tail writes."""
    from freetoken.scheduler.prefill import PrefillAdder
    from freetoken.scheduler.table import TableManager
    from freetoken.scheduler.utils import PendingReq

    total, pages = boundary + 13, 800
    pool = _pool(num_slots=32)
    pt = torch.zeros(4, pages * 64, dtype=torch.int32)
    kv = _KVPool(pages * 64)
    cm = CacheManager(pages, 64, pt, "hybrid_radix", linear_state_pool=pool, kv_pool=kv)
    # Cold request commits the exact donor page.
    ids = torch.arange(total, dtype=torch.int32)
    cold = Req(ids, 0, 0, 1, 31, SamplingParams(), cm.match_req(_pend(ids.tolist())).cuda_handle)
    cold.linear_slot_idx, cold.mamba_ping_pong = pool.alloc(1)[0], tuple(pool.alloc(2))
    cold.message_boundary_len = boundary
    cold.message_boundary_carrier = MessageBoundaryCarrier(boundary_len=boundary)
    cold.device_len = total
    cm.allocate_paged([cold])
    cold.cached_len = boundary
    cm.lock(cold.cache_handle)
    assert cm.snapshot_message_boundary(cold)
    cold.cached_len = total
    cm.cache_req(cold, finished=True)
    donor = cm._d09_entry.indices.clone()

    tm = TableManager(max_running_reqs=4, page_table=pt)
    lanes = []
    for uid in (32, 33):
        pending = PendingReq(uid, ids, SamplingParams(max_tokens=1),
                             message_boundary_len=boundary,
                             message_boundary_carrier=MessageBoundaryCarrier(boundary_len=boundary))
        lane = PrefillAdder(total, 0, cm, tm).try_add_one(pending)
        assert lane is not None and lane.message_boundary_cow_indices is not None
        lanes.append(lane)
    cm.allocate_paged(lanes)
    page = boundary // 64
    private = [pt[lane.table_idx, page * 64 : (page + 1) * 64].clone() for lane in lanes]
    donor_page = donor[-64:]
    assert all(torch.equal(kv.values[p.long()], kv.values[donor_page.long()]) for p in private)
    assert not torch.equal(private[0], donor_page) and not torch.equal(private[0], private[1])
    # A tail write in one running request cannot mutate the cached donor or the other request.
    tail = boundary % 64
    kv.values[private[0][tail:].long()] = -1
    assert torch.all(kv.values[donor_page[tail:].long()] >= 0)
    assert torch.all(kv.values[private[1][tail:].long()] >= 0)


def test_message_boundary_repeated_exact_replacement_frees_old_partial_owner():
    """Each exact hit replacement transfers full pages and frees only its old COW donor page."""
    from freetoken.scheduler.prefill import PrefillAdder
    from freetoken.scheduler.table import TableManager
    from freetoken.scheduler.utils import PendingReq

    boundary, total, pages = 20_282, 20_295, 700
    pool = _pool(num_slots=32)
    pt = torch.zeros(3, pages * 64, dtype=torch.int32)
    cm = CacheManager(pages, 64, pt, "hybrid_radix", linear_state_pool=pool, kv_pool=_KVPool(pages * 64))
    ids = torch.arange(total, dtype=torch.int32)
    cold = Req(ids, 0, 0, 1, 40, SamplingParams(), cm.match_req(_pend(ids.tolist())).cuda_handle)
    cold.linear_slot_idx, cold.mamba_ping_pong = pool.alloc(1)[0], tuple(pool.alloc(2))
    cold.message_boundary_len = boundary
    cold.message_boundary_carrier = MessageBoundaryCarrier(boundary_len=boundary)
    cold.device_len = total
    cm.allocate_paged([cold]); cold.cached_len = boundary; cm.lock(cold.cache_handle)
    assert cm.snapshot_message_boundary(cold)
    cold.cached_len = total; cm.cache_req(cold, finished=True)
    tm = TableManager(max_running_reqs=3, page_table=pt)
    released = []
    for uid in (41, 42):
        released.append(int(cm._d09_entry.indices[-64]))
        pending = PendingReq(uid, ids, SamplingParams(max_tokens=1), message_boundary_len=boundary,
                             message_boundary_carrier=MessageBoundaryCarrier(boundary_len=boundary))
        replacement = PrefillAdder(total, 0, cm, tm).try_add_one(pending)
        cm.allocate_paged([replacement])
        pool.recurrent_states[:, replacement.linear_slot_idx].fill_(boundary)
        assert cm.snapshot_message_boundary(replacement)
        replacement.cached_len = total
        cm.cache_req(replacement, finished=True)
    assert all(page in cm.free_slots.tolist() for page in released)
    cm.check_integrity()


def test_message_boundary_carrier_survives_page64_continuation_created_before_drain():
    """Overlap admits the tail before the boundary chunk drains; both Reqs share D09 state."""
    from freetoken.scheduler.prefill import ChunkedReq, PrefillAdder
    from freetoken.scheduler.table import TableManager
    from freetoken.scheduler.utils import PendingReq

    pool = _pool()
    boundary, total = 20_282, 20_400
    pt = torch.zeros(2, div_ceil(total, 64) * 64, dtype=torch.int32)
    cm = CacheManager(400, 64, pt, "hybrid_radix", linear_state_pool=pool)
    tm = TableManager(max_running_reqs=2, page_table=pt)
    carrier = MessageBoundaryCarrier(boundary_len=boundary)
    pending = PendingReq(11, torch.arange(total, dtype=torch.int32), SamplingParams(max_tokens=1),
                         message_boundary_len=boundary, message_boundary_carrier=carrier)
    first = PrefillAdder(21_000, 0, cm, tm).try_add_one(pending)
    assert isinstance(first, ChunkedReq) and first.extend_len == boundary
    # This models overlap admission: the continuation is built before the first chunk drains.
    first.cached_len = boundary
    pending.chunked_req = first
    continuation = PrefillAdder(1_000, 0, cm, tm).try_add_one(pending)
    assert continuation is not None and continuation.extend_len == total - boundary
    pool.recurrent_states[:, first.linear_slot_idx].fill_(boundary)
    assert cm.snapshot_message_boundary(first)
    assert continuation.message_boundary_carrier.snapshot_len == boundary
    assert continuation.message_boundary_carrier.snapshot_idx == 0


def test_hybrid_cache_manager_donate_then_hit():
    pool = _pool()
    page_table = torch.zeros(4, 64, dtype=torch.int32)
    cm = CacheManager(64, 1, page_table, "hybrid_radix", linear_state_pool=pool)
    assert cm.is_hybrid

    # cold match on an empty tree
    mr = cm.match_req(_pend([1, 2, 3, 4, 5]))
    assert mr.cuda_handle.cached_len == 0 and mr.mamba_value is None

    # admit req A: allocate live + ping-pong, stage KV pages, mark a ×N snapshot at boundary 4
    live, pp = pool.alloc(1)[0], tuple(pool.alloc(2))
    page_table[0, :4] = torch.tensor([100, 101, 102, 103], dtype=torch.int32)
    reqA = Req(input_ids=torch.tensor([1, 2, 3, 4, 5], dtype=torch.int32), table_idx=0,
               cached_len=4, output_len=1, uid=0, sampling_params=SamplingParams(),
               cache_handle=mr.cuda_handle)
    reqA.linear_slot_idx, reqA.mamba_ping_pong = live, pp
    reqA.mamba_next_track_idx = 1            # flipped from 0 in build_fla_metadata; frozen = pp[0]
    reqA.mamba_last_track_seqlen = 4
    cm.lock(mr.cuda_handle)

    free_before = pool.num_free_slots
    cm.cache_req(reqA, finished=False)       # donate pp[0] at boundary 4; replace it in the pair
    # pp[0] donated to the tree; a fresh replacement was alloc'd -> net free-slot count unchanged
    assert pool.num_free_slots == free_before - 1  # one replacement alloc'd (donated slot now tree-owned)
    assert reqA.mamba_ping_pong[0] != pp[0]        # slot 0 replaced; pp[0] now lives in the tree

    # req B shares the [1,2,3,4] prefix -> HIT: returns the donated snapshot + reused KV
    mrB = cm.match_req(_pend([1, 2, 3, 4, 9]))
    assert mrB.cuda_handle.cached_len == 4
    assert mrB.mamba_value == pp[0]
    assert mrB.cuda_handle.get_matched_indices().tolist() == [100, 101, 102, 103]


def test_hybrid_finish_donates_live_slot():
    pool = _pool()
    page_table = torch.zeros(4, 64, dtype=torch.int32)
    cm = CacheManager(64, 1, page_table, "hybrid_radix", linear_state_pool=pool)

    mr = cm.match_req(_pend([7, 8, 9, 10]))
    live, pp = pool.alloc(1)[0], tuple(pool.alloc(2))
    page_table[1, :3] = torch.tensor([200, 201, 202], dtype=torch.int32)
    req = Req(input_ids=torch.tensor([7, 8, 9, 10], dtype=torch.int32), table_idx=1,
              cached_len=3, output_len=1, uid=1, sampling_params=SamplingParams(),
              cache_handle=mr.cuda_handle)
    req.linear_slot_idx, req.mamba_ping_pong = live, pp
    cm.lock(mr.cuda_handle)

    cm.cache_req(req, finished=True)         # donate the live slot directly (final state)
    # ping-pong pair freed; live slot kept (now owned by the tree)
    mr2 = cm.match_req(_pend([7, 8, 9, 10]))
    assert mr2.cuda_handle.cached_len == 3 and mr2.mamba_value == live


def test_free_req_slots_idempotent():
    """C2: a finish/abort double-free of the same request must NOT push its GDN slots twice."""
    pool = _pool()
    pt = torch.zeros(4, 64, dtype=torch.int32)
    cm = CacheManager(64, 1, pt, "hybrid_radix", linear_state_pool=pool)
    live, pp = pool.alloc(1)[0], tuple(pool.alloc(2))
    req = Req(input_ids=torch.tensor([1, 2, 3], dtype=torch.int32), table_idx=0, cached_len=2,
              output_len=1, uid=0, sampling_params=SamplingParams(), cache_handle=None)
    req.linear_slot_idx, req.mamba_ping_pong = live, pp
    base = pool.num_free_slots
    cm._free_req_slots(req)
    assert pool.num_free_slots == base + 3        # live + 2 ping-pong returned once
    cm._free_req_slots(req)                        # second free (abort/finish race)
    assert pool.num_free_slots == base + 3         # idempotent: nothing pushed twice


def test_rebuild_reclaims_donated_gdn_slots():
    """C5: a runtime cache rebuild must return the discarded tree's GDN snapshot slots (idle)."""
    pool = _pool(num_slots=16)
    pt = torch.zeros(4, 64, dtype=torch.int32)
    cm = CacheManager(64, 1, pt, "hybrid_radix", linear_state_pool=pool)
    mr = cm.match_req(_pend([7, 8, 9, 10]))
    live, pp = pool.alloc(1)[0], tuple(pool.alloc(2))
    pt[1, :3] = torch.tensor([200, 201, 202], dtype=torch.int32)
    req = Req(input_ids=torch.tensor([7, 8, 9, 10], dtype=torch.int32), table_idx=1, cached_len=3,
              output_len=1, uid=1, sampling_params=SamplingParams(), cache_handle=mr.cuda_handle)
    req.linear_slot_idx, req.mamba_ping_pong = live, pp
    cm.lock(mr.cuda_handle)
    cm.cache_req(req, finished=True)              # donates `live` to the tree, frees ping-pong
    assert pool.num_free_slots < pool.num_slots - 1   # a slot is now tree-owned
    cm.rebuild(64, pt)                            # idle rebuild discards the tree
    assert pool.num_free_slots == pool.num_slots - 1  # all GDN slots reclaimed (no leak)


def test_prefill_chunk_ends_on_a_page_boundary():
    """A hybrid chunk must end page-aligned: the snapshot commit skips any other boundary."""
    from freetoken.scheduler.prefill import ChunkedReq, PrefillAdder
    from freetoken.scheduler.table import TableManager
    from freetoken.scheduler.utils import PendingReq

    pool = _pool()
    pt = torch.zeros(4, 512, dtype=torch.int32)
    cm = CacheManager(64, 64, pt, "hybrid_radix", linear_state_pool=pool)
    assert cm.prefill_chunk_align == 64
    tm = TableManager(max_running_reqs=4, page_table=pt)
    pending = PendingReq(0, torch.arange(300, dtype=torch.int32), SamplingParams(max_tokens=1))

    adder = PrefillAdder(token_budget=100, reserved_size=0, cache_manager=cm, table_manager=tm)
    req = adder.try_add_one(pending)
    assert isinstance(req, ChunkedReq) and req.extend_len == 64

    # a budget below one page keeps the unaligned chunk rather than stalling the request
    adder = PrefillAdder(token_budget=40, reserved_size=0, cache_manager=cm, table_manager=tm)
    assert adder.try_add_one(pending).extend_len == 40


def test_naive_cache_does_not_align_prefill_chunks():
    """The alignment hook is hybrid-only; every other cache keeps the raw budget chunk."""
    from freetoken.scheduler.prefill import PrefillAdder
    from freetoken.scheduler.table import TableManager
    from freetoken.scheduler.utils import PendingReq

    pt = torch.zeros(4, 512, dtype=torch.int32)
    cm = CacheManager(64, 64, pt, "radix")
    assert cm.prefill_chunk_align == 1
    tm = TableManager(max_running_reqs=4, page_table=pt)
    adder = PrefillAdder(token_budget=100, reserved_size=0, cache_manager=cm, table_manager=tm)
    pending = PendingReq(0, torch.arange(300, dtype=torch.int32), SamplingParams(max_tokens=1))
    assert adder.try_add_one(pending).extend_len == 100


def test_pool_sizing_covers_4mr_floor():
    """C6: pool must reserve the 4-slot-per-request non-evictable floor even at a tiny ratio."""
    from types import SimpleNamespace
    from freetoken.kvcache.linear_state_pool import _linear_pool_num_slots
    for mr in (1, 8, 64):
        c = SimpleNamespace(max_running_req=mr, cache_type="hybrid_radix",
                            linear_state_cache_ratio=0.1)
        assert _linear_pool_num_slots(c) >= 4 * mr + 1, (mr, _linear_pool_num_slots(c))


def _chunked_prompt_request(cm, pool, pt, ids, final_len):
    """A cold hybrid request with its whole page span allocated, mid-chunked-prefill. Returns the
    Req as the scheduler would hold it at a chunk drain: live + ping-pong slots, nothing committed."""
    mr = cm.match_req(_pend(ids))
    req = Req(input_ids=torch.tensor(ids, dtype=torch.int32), table_idx=0, cached_len=0,
              output_len=1, uid=0, sampling_params=SamplingParams(), cache_handle=mr.cuda_handle)
    req.device_len = final_len
    req.linear_slot_idx, req.mamba_ping_pong = pool.alloc(1)[0], tuple(pool.alloc(2))
    cm.lock(mr.cuda_handle)
    cm.allocate_paged([req])
    return req


def _freeze(pool, req, boundary):
    """What one chunk's forward leaves behind: the x64 checkpoint of ``boundary`` sits in the
    ping-pong slot this chunk froze (the kernel flips next_track_idx as it writes)."""
    pool.recurrent_states[:, req.mamba_ping_pong[1 - req.mamba_next_track_idx]] = float(boundary)
    req.mamba_last_track_seqlen = boundary


def _drain_chunk(cm, pool, req, boundary):
    """An INTERMEDIATE chunk's drain: freeze, then archive. The same Req object stands in for the
    continuation chain, which carries the track list by reference."""
    _freeze(pool, req, boundary)
    cm.archive_chunk_track(req)


def test_chunked_prompt_resumes_from_a_boundary_in_the_middle():
    """The bug the host bank exists for: at page_size=64 a chunked prompt had exactly ONE resume
    point -- the last x64 boundary -- because intermediate chunks are deliberately never
    cache_req'd (their pages would double-free). A prompt diverging anywhere earlier re-prefilled
    from token 0. Intermediate chunks are STILL not cache_req'd here; only their checkpoints move,
    through pinned RAM, and the final commit hangs them on the tree."""
    pool = _pool(num_slots=16, host_slots=8)
    pt = torch.zeros(4, 512, dtype=torch.int32)
    cm = CacheManager(64, 64, pt, "hybrid_radix", linear_state_pool=pool)
    ids = list(range(1, 385))                       # 3 chunks of 128 -> x64 boundaries 64/192/320
    req = _chunked_prompt_request(cm, pool, pt, ids, 384)
    device_free = pool.num_free_slots

    _drain_chunk(cm, pool, req, 64)
    _drain_chunk(cm, pool, req, 192)
    banked = dict(req.mamba_host_tracks)            # boundary -> bank slot
    assert sorted(banked) == [64, 192] and banked[64] != banked[192]
    assert pool.num_free_slots == device_free, "archiving owns no pages and no device slots"
    assert pool.num_free_host_slots == 5

    req.cached_len = 384
    req.mamba_next_track_idx = 1
    _freeze(pool, req, 320)                         # the final chunk: committed, not archived
    cm.cache_req(req, finished=False)               # device at 320, bank at 64/192

    assert req.mamba_host_tracks is None
    assert pool.num_free_host_slots == 5, "both boundaries landed, nothing was dropped"

    hit_mid = cm.match_req(_pend(ids[:131]))        # diverges at token 130, inside the 2nd chunk
    assert hit_mid.cuda_handle.cached_len == 64, "resume from the archived boundary, not from 0"
    assert hit_mid.mamba_host == banked[64]
    assert hit_mid.mamba_value is None

    hit_late = cm.match_req(_pend(ids[:201]))
    assert hit_late.cuda_handle.cached_len == 192 and hit_late.mamba_host == banked[192]

    hit_end = cm.match_req(_pend(ids))              # the device checkpoint still wins at its own end
    assert hit_end.cuda_handle.cached_len == 320 and hit_end.mamba_value is not None

    # A bank resume must carry the actual state, not just a length.
    fresh = pool.alloc(1)[0]
    pool.from_host(hit_mid.mamba_host, fresh)
    assert pool.recurrent_states[:, fresh].unique().tolist() == [64.0]

    cm.cache_req(req, finished=True)               # idle now: only then is check_integrity valid
    cm.check_integrity()


def test_no_bank_keeps_the_old_single_resume_point_behavior():
    """--mamba-host-slots 0 (the default) must be byte-for-byte the previous engine: the archive
    is a no-op, so a mid-prompt fork still re-prefills everything and only the last boundary is
    reusable. This is the reversibility guarantee for the flag."""
    pool = _pool(num_slots=16, host_slots=0)
    assert pool.num_host_slots <= 1
    pt = torch.zeros(4, 512, dtype=torch.int32)
    cm = CacheManager(64, 64, pt, "hybrid_radix", linear_state_pool=pool)
    ids = list(range(1, 385))
    req = _chunked_prompt_request(cm, pool, pt, ids, 384)

    _drain_chunk(cm, pool, req, 64)
    _drain_chunk(cm, pool, req, 192)
    assert req.mamba_host_tracks is None, "no bank, no archive"

    req.cached_len = 384
    req.mamba_next_track_idx = 1
    _freeze(pool, req, 320)
    cm.cache_req(req, finished=False)

    assert cm.match_req(_pend(ids[:131])).cuda_handle.cached_len == 0
    assert cm.match_req(_pend(ids[:201])).cuda_handle.cached_len == 0
    assert cm.match_req(_pend(ids)).cuda_handle.cached_len == 320
    cm.cache_req(req, finished=True)
    cm.check_integrity()


def test_host_bank_survives_a_rebuild():
    """A runtime cache rebuild discards the tree that owned the bank checkpoints; the bank
    free-list must come back whole or the slots leak for the process lifetime."""
    pool = _pool(num_slots=16, host_slots=8)
    pt = torch.zeros(4, 512, dtype=torch.int32)
    cm = CacheManager(64, 64, pt, "hybrid_radix", linear_state_pool=pool)
    ids = list(range(1, 257))
    req = _chunked_prompt_request(cm, pool, pt, ids, 256)
    _drain_chunk(cm, pool, req, 64)
    req.cached_len = 256
    req.mamba_next_track_idx = 1
    _freeze(pool, req, 192)
    cm.cache_req(req, finished=False)
    assert pool.num_free_host_slots < 7             # a checkpoint is bank-resident now
    cm.rebuild(64, pt)
    assert pool.num_free_host_slots == 7


def test_archive_lands_in_the_list_the_continuation_already_carries():
    """Overlap scheduling builds the NEXT chunk's Req before this chunk's drain archives its
    boundary, so the archive must fill the list that already exists at admission -- a list the
    drain creates itself would live on the abandoned Req and the commit would attach nothing.
    The continuation here mirrors what PrefillAdder._add_one_req copies (same object, not a copy)."""
    pool = _pool(num_slots=16, host_slots=8)
    pt = torch.zeros(4, 512, dtype=torch.int32)
    cm = CacheManager(64, 64, pt, "hybrid_radix", linear_state_pool=pool)
    ids = list(range(1, 129))
    chunk1 = _chunked_prompt_request(cm, pool, pt, ids, 128)
    chunk1.mamba_host_tracks = []                       # what admission seeds when the bank is on
    chunk2 = SimpleNamespace(mamba_ping_pong=chunk1.mamba_ping_pong,
                             mamba_next_track_idx=chunk1.mamba_next_track_idx,
                             mamba_last_track_seqlen=chunk1.mamba_last_track_seqlen,
                             mamba_host_tracks=chunk1.mamba_host_tracks,
                             input_ids=chunk1.input_ids)
    _drain_chunk(cm, pool, chunk1, 64)                  # the drain runs AFTER chunk2 was built
    assert chunk2.mamba_host_tracks == chunk1.mamba_host_tracks == [(64, chunk2.mamba_host_tracks[0][1])]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name}: PASS")
