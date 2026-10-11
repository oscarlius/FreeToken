"""Strict CPU-only D09 Scheduler replay using sealed token arrays and production track metadata."""
import contextlib
import hashlib
import inspect
import json
import os
import struct
import subprocess
from pathlib import Path
from types import SimpleNamespace

os.environ.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import torch
from freetoken.attention.linear import build_fla_metadata
from freetoken.core import Batch, Context, MessageBoundaryCarrier, Req, SamplingParams, set_global_ctx
from freetoken.distributed import DistributedInfo
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
import freetoken
import freetoken.engine
from freetoken.scheduler.scheduler import ForwardInput, Scheduler, SchedulerConfig

INPUTS = Path("/data2/FreeToken/development/d09_gpu_reapplication_20261010/D09_T17_EXACT_INPUTS.json")
RAW_ROOT = Path("/data2/_shared/runs/ft_rounds/E2-D09-T17-reapply-bd57-20261010")
EXACT_INPUTS_SHA = "b21a29e47d6dc5fb5be9d32e98bc446ed8a1f5d625efd7774aad31d2afdde6f9"
RAW_PINS = {"round.json":"a6655b5920069ada590f515dc0a612e8fb65b33045c48ba56021b235b4750ee5", "config.json":"4454e172b679a7aed0731ec8f32e18364cf052fe7cfebe1cdbdeb02550450480", "services/hot_c0_p20282_t1020/call_3.binding.json":"3bfc9c87456929f594666b171c5cfb4f899e90afb0077e4980b9feca9ca37568", "services/hot_c0_p20282_t1020/call_4.binding.json":"818b87b48328070aecbdfa530ce7521383d122f510c7cdf0f9d7d6712ba455fb"}
DONOR_SHA = "24068f95180ac5cca644024d56f749a341df16ceb35574e41c83bb396471142a"
TARGET_SHA = "22ed510abb88eaaac15e6103fe292ba23d641e18ea01c14fa1f2dce6c4790fbc"
ORIGINAL = {name: getattr(torch.cuda, name) for name in ("Stream", "set_stream", "stream")}
PIN_ROOT = Path("/data2/FreeToken/wt/d05_hbug_candidate_20261010/python").resolve()
PIN_COMMIT = "bd57cfdccc2a935d46cb0a89b8b36be7a18706de"
def source_receipt():
    imported = Path(freetoken.__file__).resolve(); assert PIN_ROOT in imported.parents, imported
    root=PIN_ROOT.parent
    assert subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()==PIN_COMMIT
    files=["freetoken/scheduler/cache.py","freetoken/scheduler/scheduler.py","freetoken/core.py","freetoken/kvcache/linear_state_pool.py","freetoken/attention/linear.py"]
    blobs={}
    for rel in files:
        disk=(PIN_ROOT/rel).read_bytes(); blob=subprocess.check_output(["git","-C",str(root),"rev-parse",f"HEAD:python/{rel}"],text=True).strip()
        assert subprocess.check_output(["git","-C",str(root),"hash-object",str(PIN_ROOT/rel)],text=True).strip()==blob
        blobs[rel]={"git_blob":blob,"sha256":hashlib.sha256(disk).hexdigest()}
    from freetoken.scheduler.cache import CacheManager
    funcs={"CacheManager._cache_req_hybrid":CacheManager._cache_req_hybrid,"CacheManager._commit_d09_exact":CacheManager._commit_d09_exact,"Scheduler._forward":Scheduler._forward,"Req.complete_one":Req.complete_one,"build_fla_metadata":build_fla_metadata}
    return {"import_file":str(imported),"commit":PIN_COMMIT,"files":blobs,"function_sha256":{n:hashlib.sha256(inspect.getsource(f).encode()).hexdigest() for n,f in funcs.items()}}
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
    assert hashlib.sha256(INPUTS.read_bytes()).hexdigest() == EXACT_INPUTS_SHA
    for rel, expected in RAW_PINS.items():
        assert hashlib.sha256((RAW_ROOT / rel).read_bytes()).hexdigest() == expected, rel
    doc=json.loads(INPUTS.read_text())
    assert doc["schema"] == "ft_d09_t17_exact_ids/v1"
    binding=doc["source_binding"]
    assert binding == {"prediction_manifest_v4_sha256":"edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9", "source_manifest_sha256":"5d4995e35d3f15eb6662f976a059c1c68fadaccadab319533bc5fee11f5172cd", "trace":"D:\\00.开发\\2026\\03-模型实验\\freetoken\\freetoken\\development\\d09_prediction_20261009\\source\\trace.json", "trace_sha256":"055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899"}
    cell=next(c for c in doc["cells"] if c.get("donor_ids_sha256") == DONOR_SHA and c.get("target_ids_sha256") == TARGET_SHA)
    expected={"boundary":20282,"common_prefix_tokens":20283,"ordinary_page_floor":20224,"prompt_tokens":21302,"round":7,"tail":1020,"generation_turn_at":21297,"last_two_im_start":[20282,21297],"edit_applied":True}
    assert {k:cell[k] for k in expected} == expected
    donor,target=cell["donor_ids"],cell["target_ids"]
    assert len(donor)==len(target)==21302 and digest(donor)==DONOR_SHA and digest(target)==TARGET_SHA
    return torch.tensor(donor, dtype=torch.int32),torch.tensor(target, dtype=torch.int32), {"exact_inputs_sha256":EXACT_INPUTS_SHA,"raw_pins":RAW_PINS,"selected_cell":expected,"source_binding":binding}

def main():
    torch.cuda.Stream=lambda *a,**k:object(); PATCHED.append("torch.cuda.Stream")
    torch.cuda.set_stream=lambda *a,**k:None; PATCHED.append("torch.cuda.set_stream")
    torch.cuda.stream=lambda *a,**k:contextlib.nullcontext(); PATCHED.append("torch.cuda.stream")
    old=freetoken.engine.Engine; freetoken.engine.Engine=CpuEngine
    try:
        cfg=SchedulerConfig(model_path="/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",tp_info=DistributedInfo(0,1),dtype=torch.bfloat16,cache_type="hybrid_radix",page_size=64,max_running_req=4,offline_mode=True)
        scheduler=Scheduler(cfg); pins=source_receipt(); scheduler.message_boundary_ckpt=True
        cache,pool=scheduler.cache_manager,scheduler.engine.linear_state_pool
        receipts=[]
        original_snapshot=cache.snapshot_message_boundary
        original_commit=cache._commit_d09_exact
        def snapshot_observer(request):
            before=(request.cached_len, request.message_boundary_carrier.snapshot_len if request.message_boundary_carrier else None)
            result=original_snapshot(request)
            receipts.append({"event":"snapshot_message_boundary","before":before,"result":result,
                "after_cached":request.cached_len,"carrier_snapshot":request.message_boundary_carrier.snapshot_len if request.message_boundary_carrier else None,"carrier_idx":request.message_boundary_carrier.snapshot_idx if request.message_boundary_carrier else None})
            return result
        def commit_observer(request, old_handle, page_indices, boundary):
            guard={"boundary":boundary,"idx":request.message_boundary_carrier.snapshot_idx if request.message_boundary_carrier else request.message_boundary_snapshot_idx,
                "has_pingpong":request.mamba_ping_pong is not None,"old_cached":old_handle.cached_len,
                "old_is_d09":type(old_handle).__name__ == "_D09BoundaryHandle"}
            result=original_commit(request, old_handle, page_indices, boundary)
            receipts.append({"event":"_commit_d09_exact","guard":guard,"result":result})
            return result
        # Transparent delegates: original methods make every product decision and mutation.
        cache.snapshot_message_boundary=snapshot_observer
        cache._commit_d09_exact=commit_observer
        donor_ids,target_ids,input_receipt=inputs()
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
        true_snapshots=[r for r in receipts if r["event"]=="snapshot_message_boundary" and r["result"] is True]
        commits=[r for r in receipts if r["event"]=="_commit_d09_exact"]
        assert len(true_snapshots)==1 and true_snapshots[0]["after_cached"]==20282 and true_snapshots[0]["carrier_snapshot"]==20282 and true_snapshots[0]["carrier_idx"] is not None
        assert len(commits)==1 and commits[0]["guard"] == {"boundary":20282,"idx":true_snapshots[0]["carrier_idx"],"has_pingpong":True,"old_cached":20160,"old_is_d09":False} and commits[0]["result"] is False
        match=cache.match_req(SimpleNamespace(input_ids=target_ids,input_len=len(target_ids)))
        assert match.cuda_handle.cached_len==20160, match.cuda_handle.cached_len
        # UID1 actual admission/match; do not execute a synthetic donor or alter match result.
        target=req(target_ids,1,1,match.cuda_handle,match.cuda_handle.cached_len)
        slots(pool,target); cache.allocate_paged([target]); cache.lock(target.cache_handle)
        print(json.dumps({"status":"strict_scheduler_d09","donor_geometry":[[0,20224],[20224,20282],[20282,21302]],
            "target_admission_cached_tokens":match.cuda_handle.cached_len,"native_track_boundary":track20160,
            "d09_exact_boundary":None,"d09_commit_guard":"old_handle_cached_nonzero", "receipts":receipts, "input_pin":input_receipt, "source_pin":pins, "complete_one_only":True,"patched":PATCHED},sort_keys=True))
    finally:
        freetoken.engine.Engine=old
        for name,value in ORIGINAL.items(): setattr(torch.cuda,name,value)
if __name__=="__main__": main()
