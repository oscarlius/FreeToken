"""Strict CPU-only Scheduler._forward D05 replay.  No request-length writes occur in the model seam."""
import contextlib
import json
import os
from types import SimpleNamespace

os.environ.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import torch
from freetoken.core import Batch, Context, Req, SamplingParams, set_global_ctx
from freetoken.distributed import DistributedInfo
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
import freetoken.engine
from freetoken.scheduler.scheduler import Scheduler, SchedulerConfig

PATCHED = []
ORIGINAL = {name: getattr(torch.cuda, name) for name in ("Stream", "set_stream", "stream")}

class CpuEngine:
    def __init__(self, config):
        group = LinearGatedDeltaGroupConfig(name="linear", layer_ids=(0,), num_key_heads=2,
            num_value_heads=4, key_head_dim=16, value_head_dim=16, conv_kernel_dim=4, output_gate="silu")
        self.device = torch.device("cpu")
        self.stream = None
        self.num_pages = 512
        self.page_table = torch.zeros(4, self.num_pages * config.page_size, dtype=torch.int32)
        self.linear_state_pool = LinearStatePool(group=group, num_slots=16, dtype=torch.bfloat16,
            device=self.device, tp_size=1)
        self.kv_cache = self.moe_offload_cache = self.encoder_cache = self.tp_cpu_group = None
        ctx = Context(config.page_size)
        ctx.page_table = self.page_table
        ctx.linear_state_pool = self.linear_state_pool
        set_global_ctx(ctx)

    def forward_batch(self, batch, sample_args):
        # Model-output seam only. Req bookkeeping remains production Req.complete_one().
        for req in batch.reqs:
            req.complete_one()
        return SimpleNamespace(next_tokens_gpu=torch.ones(len(batch.reqs), dtype=torch.int32))

def slots(pool, req):
    req.linear_slot_idx = pool.alloc(1)[0]
    req.mamba_ping_pong = tuple(pool.alloc(2))

def make_req(ids, uid, table, handle):
    return Req(ids.to(torch.int32), table, 0, 2, uid, SamplingParams(), handle)

def main():
    torch.cuda.Stream = lambda *a, **k: object(); PATCHED.append("torch.cuda.Stream")
    torch.cuda.set_stream = lambda *a, **k: None; PATCHED.append("torch.cuda.set_stream")
    torch.cuda.stream = lambda *a, **k: contextlib.nullcontext(); PATCHED.append("torch.cuda.stream")
    old_engine = freetoken.engine.Engine
    freetoken.engine.Engine = CpuEngine
    try:
        cfg = SchedulerConfig(model_path="/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",
            tp_info=DistributedInfo(0,1), dtype=torch.bfloat16, cache_type="hybrid_radix",
            page_size=64, max_running_req=4, offline_mode=True)
        scheduler = Scheduler(cfg)
        cache, pool = scheduler.cache_manager, scheduler.engine.linear_state_pool
        ids = torch.arange(13555, dtype=torch.int32)
        # The recorded D05 donor ends at the aligned 13376-prefix; its own next
        # token supplies the production complete_one() transition into that state.
        donor_ids = ids[:13377]
        donor = make_req(donor_ids, 6, 0, cache.match_req(SimpleNamespace(input_ids=donor_ids, input_len=len(donor_ids))).cuda_handle)
        slots(pool, donor); cache.allocate_paged([donor]); cache.lock(donor.cache_handle)
        while donor.cached_len < 13376:
            donor.complete_one()
        cache.cache_req(donor, finished=True)
        hit = cache.match_req(SimpleNamespace(input_ids=ids, input_len=len(ids))).cuda_handle
        assert hit.cached_len == 13376, hit.cached_len
        target = make_req(ids, 7, 1, hit)
        slots(pool, target); target.cached_len = hit.cached_len
        # Raw pre-forward state: the 13554th token is the one processed by _forward.
        target.device_len = 13554
        cache.allocate_paged([target]); cache.lock(target.cache_handle)
        batch = Batch([target], "decode")
        table = torch.tensor([target.table_idx], dtype=torch.int64)
        pos = torch.tensor([target.cached_len], dtype=torch.int64)
        scheduler._forward((batch, None, (table, pos), (table, pos)))
        assert target.cached_len == 13554, target.cached_len
        cache.cache_req(target, finished=True)
        replay = cache.match_req(SimpleNamespace(input_ids=ids, input_len=len(ids))).cuda_handle.cached_len
        print(json.dumps({"status":"strict_scheduler_d05", "cached_tokens":replay,
            "forward_cached_len":target.cached_len, "complete_one_only":True, "patched":PATCHED}, sort_keys=True))
    finally:
        freetoken.engine.Engine = old_engine
        for name, value in ORIGINAL.items():
            setattr(torch.cuda, name, value)

if __name__ == "__main__":
    main()
