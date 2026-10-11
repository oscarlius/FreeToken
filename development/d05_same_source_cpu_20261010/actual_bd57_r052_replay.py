"""CPU-only replay of R052a UID7 through the actual bd57 CacheManager/Scheduler seam.

This imports the candidate source via PYTHONPATH and never starts a server, HTTP client,
CUDA model, or subprocess.  It recreates the retained geometry: an aligned UID6 donor at
13376, UID7 decode to unaligned 13554, then a matching follow-up admission.
"""
from __future__ import annotations

from types import SimpleNamespace

import torch

from freetoken.core import Req, SamplingParams
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
from freetoken.scheduler.cache import CacheManager
from freetoken.scheduler.scheduler import ForwardInput, Scheduler

PAGE = 64
DONOR = 13_376
TARGET_FINAL = 13_554
TARGET_FLOOR = 13_504


def _pool() -> LinearStatePool:
    group = LinearGatedDeltaGroupConfig(
        name="linear", layer_ids=(0,), num_key_heads=2, num_value_heads=4,
        key_head_dim=16, value_head_dim=16, conv_kernel_dim=4, output_gate="silu",
    )
    return LinearStatePool(group=group, num_slots=16, dtype=torch.bfloat16,
                           device=torch.device("cpu"), tp_size=1)


def _pending(ids: torch.Tensor):
    return SimpleNamespace(input_ids=ids.to(torch.int32), input_len=len(ids))


def _req(ids: torch.Tensor, *, uid: int, table_idx: int, cached_len: int, handle) -> Req:
    req = Req(ids.to(torch.int32), table_idx, cached_len, 1, uid, SamplingParams(), handle)
    req.device_len = len(ids)
    return req


def _slots(pool: LinearStatePool, req: Req) -> None:
    req.linear_slot_idx = pool.alloc(1)[0]
    req.mamba_ping_pong = tuple(pool.alloc(2))


def replay() -> dict[str, int | bool | str]:
    pool = _pool()
    page_table = torch.zeros(3, 512 * PAGE, dtype=torch.int32)
    cache = CacheManager(512, PAGE, page_table, "hybrid_radix", linear_state_pool=pool)

    # Actual generic CacheManager finish creates the retained UID6-aligned donor.
    donor_ids = torch.arange(DONOR + 1, dtype=torch.int32)
    donor_match = cache.match_req(_pending(donor_ids))
    donor = _req(donor_ids, uid=6, table_idx=0, cached_len=0, handle=donor_match.cuda_handle)
    _slots(pool, donor)
    cache.allocate_paged([donor])
    donor.cached_len = DONOR
    cache.lock(donor.cache_handle)
    cache.cache_req(donor, finished=True)

    target_ids = torch.arange(TARGET_FINAL, dtype=torch.int32)
    hit = cache.match_req(_pending(target_ids))
    assert hit.cuda_handle.cached_len == DONOR
    assert hit.mamba_value is not None

    # This is the actual scheduler decode seam.  It deliberately cannot create a D09 marker:
    # batch is decode, message-boundary checkpointing is disabled, and no tool anchor is set.
    target = _req(target_ids, uid=7, table_idx=1, cached_len=DONOR, handle=hit.cuda_handle)
    _slots(pool, target)
    page_table[target.table_idx, :DONOR].copy_(hit.cuda_handle.get_matched_indices())
    cache.allocate_paged([target])
    cache.lock(target.cache_handle)
    scheduler = object.__new__(Scheduler)
    scheduler.cache_manager = cache
    scheduler.message_boundary_ckpt = False
    scheduler.toolcall_anchor_id = None
    scheduler.token_pool = {0: torch.tensor([1], dtype=torch.int32)}
    scheduler.decode_manager = SimpleNamespace(filter_reqs=lambda reqs: None)

    def forward(batch, sample_args):
        # CPU stand-in only for the model side effect; all scheduling/cache dispatch is actual.
        target.cached_len = TARGET_FINAL
        target.device_len = TARGET_FINAL
        return SimpleNamespace(next_tokens_gpu=torch.tensor([1], dtype=torch.int32))

    scheduler.engine = SimpleNamespace(forward_batch=forward)
    scheduler._forward(ForwardInput(SimpleNamespace(reqs=[target], is_prefill=False), None, 0, 1))
    assert target.mamba_last_track_seqlen is None
    assert cache._d09_entry is None
    cache.cache_req(target, finished=True)

    followup = cache.match_req(_pending(target_ids))
    return {
        "page_size": PAGE,
        "uid6_donor_cached_len": DONOR,
        "uid7_final_cached_len": TARGET_FINAL,
        "floor_64": TARGET_FLOOR,
        "followup_cached_len": followup.cuda_handle.cached_len,
        "missing_to_floor": TARGET_FLOOR - followup.cuda_handle.cached_len,
        "d09_entry_created": cache._d09_entry is not None,
        "decode_created_track": target.mamba_last_track_seqlen is not None,
        "classification": "different_source_from_d09_explicit_boundary_path",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(replay(), sort_keys=True))
