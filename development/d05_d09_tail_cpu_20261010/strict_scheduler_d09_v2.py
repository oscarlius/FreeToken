"""Strict CPU-only D09 Scheduler replay using sealed token arrays and production track metadata."""
import contextlib
import hashlib
import json
import os
import struct
from pathlib import Path
from types import SimpleNamespace

os.environ.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import torch
from freetoken.attention.linear import build_fla_metadata
from freetoken.core import Batch, Context, MessageBoundaryCarrier, Req, SamplingParams, set_global_ctx
from freetoken.distributed import DistributedInfo
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
import freetoken.engine
from freetoken.scheduler.scheduler import ForwardInput, Scheduler, SchedulerConfig

INPUTS = Path("/data2/FreeToken/development/d09_gpu_reapplication_20261010/D09_T17_EXACT_INPUTS.json")
DONOR_SHA = "24068f95180ac5cca644024d56f749a341df16ceb35574e41c83bb396471142a"
TARGET_SHA = "22ed510abb88eaaac15e6103fe292ba23d641e18ea01c14fa1f2dce6c4790fbc"
ORIGINAL = {name: getattr(torch.cuda, name) for name in ("Stream", "set_stream", "stream")}
PATCHED = []

class CpuEngine:
    def __init__(self, config):
        group = LinearGatedDeltaGroupConfig(name="linear", layer_ids=(0,), num_key_heads=2,
            num_value_heads=4, key_head_dim=16, value_head_dim=16, conv_kernel_dim=4, output_gate="silu")
        self.device = torch.device("cpu"); self.stream = None; self.num_pages = 512
        self.page_table = torch.zeros(4, self.num_pages * config.page_size, dtype=torch.int32)
        self.linear_state_pool = LinearStatePool(group=group, num_slots=16, dtype=torch.bfloat16,
            device=self.device, tp_size=1)
        self.kv_cache = self.moe_offload_cache = self.encoder_cache = self.tp_cpu_group = None
        ctx = Context(config.page_size); ctx.page_table = self.page_table; ctx.linear_state_pool = self.linear_state_pool
        set_global_ctx(ctx)
    def forward_batch(self, batch, sample_args):
        # Sole model seam: product Req bookkeeping carries all length transitions.
        for req in batch.reqs: req.complete_one()
        return SimpleNamespace(next_tokens_gpu=torch.ones(len(batch.reqs), dtype=torch.int32))

def digest(ids): return hashlib.sha256(struct.pack("<" + "i" * len(ids), *ids)).hexdigest()
def slots(pool, req):
    req.linear_slot_idx = pool.alloc(1)[0]; req.mamba_ping_pong = tuple(pool.alloc(2))
def req(ids, uid, table, handle, cached=0): return Req(ids.to(torch.int32), table, cached, 32, uid, SamplingParams(ignore_eos=True, max_tokens=32), handle)
def fw(scheduler, request, phase, table):
    batch = Batch([request], phase)
    if phase == "prefill":
        batch.padded_reqs = [request]
        build_fla_metadata(batch, torch.device("cpu"))  # production track computation mutates only its documented fields.
    mapping = (torch.tensor([table], dtype=torch.int64), torch.tensor([request.cached_len], dtype=torch.int64))
    scheduler._forward(ForwardInput(batch, None, mapping, mapping))

def inputs():
    doc=json.loads(INPUTS.read_text())
    cell=next(c for c in doc["cells"] if c.get("donor_ids_sha256") == DONOR_SHA and c.get("target_ids_sha256") == TARGET_SHA)
    donor,target=cell["donor_ids"],cell["target_ids"]
    assert len(donor)==len(target)==21302 and digest(donor)==DONOR_SHA and digest(target)==TARGET_SHA
    return torch.tensor(donor),torch.tensor(target)

def main():
    torch.cuda.Stream=lambda *a,**k:object(); PATCHED.append("torch.cuda.Stream")
    torch.cuda.set_stream=lambda *a,**k:None; PATCHED.append("torch.cuda.set_stream")
    torch.cuda.stream=lambda *a,**k:contextlib.nullcontext(); PATCHED.append("torch.cuda.stream")
    old=freetoken.engine.Engine; freetoken.engine.Engine=CpuEngine
    try:
        cfg=SchedulerConfig(model_path="/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",tp_info=DistributedInfo(0,1),dtype=torch.bfloat16,cache_type="hybrid_radix",page_size=64,max_running_req=4,offline_mode=True)
        scheduler=Scheduler(cfg); scheduler.message_boundary_ckpt=True
        cache,pool=scheduler.cache_manager,scheduler.engine.linear_state_pool
        donor_ids,target_ids=inputs()
        donor=req(donor_ids,0,0,cache.match_req(SimpleNamespace(input_ids=donor_ids,input_len=len(donor_ids))).cuda_handle)
        slots(pool,donor); donor.message_boundary_len=20282; donor.message_boundary_carrier=MessageBoundaryCarrier(boundary_len=20282)
        cache.allocate_paged([donor]); cache.lock(donor.cache_handle)
        # UID0 raw segment 0 -> 20224. device_len is sealed pre-forward state; _forward calls complete_one().
        donor.device_len=20224; fw(scheduler,donor,"prefill",0)
        assert donor.cached_len==20224 and donor.mamba_last_track_seqlen==20160, (donor.cached_len,donor.mamba_last_track_seqlen)
        track20160=donor.mamba_last_track_seqlen
        cache.cache_req(donor,finished=False)
        # UID0 raw segment 20224 -> 20282: no x64 track, then real Scheduler boundary snapshot.
        donor.device_len=20282; fw(scheduler,donor,"prefill",0)
        assert donor.cached_len==20282 and donor.message_boundary_carrier.snapshot_len==20282
        # UID0 raw tail 20282 -> 21302 and normal finished D09 commit.
        donor.device_len=21302; fw(scheduler,donor,"prefill",0)
        cache.cache_req(donor,finished=True)
        # The preceding 20160 hybrid handle is nonzero, so the production guard at
        # CacheManager._commit_d09_exact:655 rejects the literal 20282 entry.  The
        # already-donated native 20160 track remains the actual reusable boundary.
        assert cache._d09_entry is None
        match=cache.match_req(SimpleNamespace(input_ids=target_ids,input_len=len(target_ids)))
        assert match.cuda_handle.cached_len==20160, match.cuda_handle.cached_len
        # UID1 actual admission/match; do not execute a synthetic donor or alter match result.
        target=req(target_ids,1,1,match.cuda_handle,match.cuda_handle.cached_len)
        slots(pool,target); cache.allocate_paged([target]); cache.lock(target.cache_handle)
        print(json.dumps({"status":"strict_scheduler_d09","donor_geometry":[[0,20224],[20224,20282],[20282,21302]],
            "target_admission_cached_tokens":match.cuda_handle.cached_len,"native_track_boundary":track20160,
            "d09_exact_boundary":None,"d09_commit_guard":"old_handle_cached_nonzero", "complete_one_only":True,"patched":PATCHED},sort_keys=True))
    finally:
        freetoken.engine.Engine=old
        for name,value in ORIGINAL.items(): setattr(torch.cuda,name,value)
if __name__=="__main__": main()
