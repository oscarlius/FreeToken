"""Pinned batch164 D09 v7 replay against the candidate Scheduler/CacheManager seam.

CPU only.  The sole replacement is CpuEngine.forward_batch's deterministic state
write; Scheduler, CacheManager, Req, FLA metadata and LinearStatePool are the
candidate source.  It refuses mismatched sealed inputs/raw evidence/source pins.
"""
from __future__ import annotations
import argparse, contextlib, hashlib, inspect, json, os, struct, subprocess
from pathlib import Path
from types import SimpleNamespace
os.environ.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import torch
from freetoken.attention.linear import build_fla_metadata
from freetoken.core import Batch, Context, MessageBoundaryCarrier, Req, SamplingParams, set_global_ctx
from freetoken.distributed import DistributedInfo
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig, SlotStateSpec
import freetoken, freetoken.engine
from freetoken.scheduler.scheduler import ForwardInput, Scheduler, SchedulerConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUTS = ROOT / "development/d09_gpu_reapplication_20261010/protocol_t17/D09_T17_EXACT_INPUTS.json"
EXACT_INPUTS_SHA = "b21a29e47d6dc5fb5be9d32e98bc446ed8a1f5d625efd7774aad31d2afdde6f9"
RAW_PINS = {"round.json":"a6655b5920069ada590f515dc0a612e8fb65b33045c48ba56021b235b4750ee5", "config.json":"4454e172b679a7aed0731ec8f32e18364cf052fe7cfebe1cdbdeb02550450480", "services/hot_c0_p20282_t1020/call_3.binding.json":"3bfc9c87456929f594666b171c5cfb4f899e90afb0077e4980b9feca9ca37568", "services/hot_c0_p20282_t1020/call_4.binding.json":"818b87b48328070aecbdfa530ce7521383d122f510c7cdf0f9d7d6712ba455fb"}
DONOR_SHA = "24068f95180ac5cca644024d56f749a341df16ceb35574e41c83bb396471142a"
TARGET_SHA = "22ed510abb88eaaac15e6103fe292ba23d641e18ea01c14fa1f2dce6c4790fbc"
BOUNDARY, NATIVE = 20_282, 20_160
ORIGINAL = {name: getattr(torch.cuda, name) for name in ("Stream", "set_stream", "stream")}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(ids): return hashlib.sha256(struct.pack("<" + "i" * len(ids), *ids)).hexdigest()
def _group(): return LinearGatedDeltaGroupConfig(name="linear", layer_ids=(0,), num_key_heads=2, num_value_heads=4, key_head_dim=16, value_head_dim=16, conv_kernel_dim=4, output_gate="silu")
def stamp(pool, slot, value):
    pool.conv_states[:, slot].fill_(value); pool.recurrent_states[:, slot].fill_(value + 1)
    for tensor in pool.slot_states.values(): tensor[:, slot].fill_(value + 2)

def source_receipt(expected_commit: str | None):
    imported = Path(freetoken.__file__).resolve(); pin_root = imported.parent.parent
    files=["freetoken/scheduler/cache.py","freetoken/scheduler/scheduler.py","freetoken/core.py","freetoken/kvcache/linear_state_pool.py","freetoken/attention/linear.py"]
    receipt={"import_file":str(imported),"python_root":str(pin_root),"files":{rel:sha(pin_root/rel) for rel in files}}
    root=pin_root.parent
    try: receipt["git_commit"]=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    except (OSError, subprocess.CalledProcessError): receipt["git_commit"]=None
    if expected_commit and receipt["git_commit"] != expected_commit: raise RuntimeError("candidate source commit differs")
    funcs={"CacheManager._cache_req_hybrid":__import__("freetoken.scheduler.cache",fromlist=["CacheManager"]).CacheManager._cache_req_hybrid,"CacheManager._commit_d09_exact":__import__("freetoken.scheduler.cache",fromlist=["CacheManager"]).CacheManager._commit_d09_exact,"Scheduler._forward":Scheduler._forward,"Req.complete_one":Req.complete_one,"build_fla_metadata":build_fla_metadata}
    receipt["function_sha256"]={name:hashlib.sha256(inspect.getsource(fn).encode()).hexdigest() for name,fn in funcs.items()}
    return receipt

class CpuEngine:
    def __init__(self, config):
        self.device=torch.device("cpu"); self.stream=None; self.num_pages=512
        self.page_table=torch.zeros(4,self.num_pages*config.page_size,dtype=torch.int32)
        self.linear_state_pool=LinearStatePool(group=_group(),num_slots=20,dtype=torch.bfloat16,device=self.device,tp_size=1,slot_states=(SlotStateSpec("ple_conv",(4,3),layer_ids=(0,)),SlotStateSpec("ple_context",(3,),dtype=torch.int32)))
        self.kv_cache=self.moe_offload_cache=self.encoder_cache=self.tp_cpu_group=None
        ctx=Context(config.page_size);ctx.page_table=self.page_table;ctx.linear_state_pool=self.linear_state_pool;set_global_ctx(ctx)
    def forward_batch(self,batch,sample_args):
        for request in batch.reqs:
            stamp(self.linear_state_pool,request.linear_slot_idx,int(request.device_len)); request.complete_one()
        return SimpleNamespace(next_tokens_gpu=torch.ones(len(batch.reqs),dtype=torch.int32))

def inputs(path, raw_root):
    if sha(path)!=EXACT_INPUTS_SHA: raise RuntimeError("sealed exact input SHA differs")
    for rel, expected in RAW_PINS.items():
        if sha(raw_root/rel)!=expected: raise RuntimeError(f"raw batch164 pin differs: {rel}")
    doc=json.loads(Path(path).read_text());
    if doc.get("schema")!="ft_d09_t17_exact_ids/v1": raise RuntimeError("exact input schema differs")
    cell=next(c for c in doc["cells"] if c.get("donor_ids_sha256")==DONOR_SHA and c.get("target_ids_sha256")==TARGET_SHA)
    expected={"boundary":BOUNDARY,"common_prefix_tokens":20283,"ordinary_page_floor":20224,"prompt_tokens":21302,"round":7,"tail":1020,"generation_turn_at":21297,"last_two_im_start":[20282,21297],"edit_applied":True}
    if {k:cell[k] for k in expected} != expected: raise RuntimeError("selected batch164 v7 cell differs")
    donor,target=cell["donor_ids"],cell["target_ids"]
    if digest(donor)!=DONOR_SHA or digest(target)!=TARGET_SHA: raise RuntimeError("sealed token digest differs")
    return torch.tensor(donor,dtype=torch.int32),torch.tensor(target,dtype=torch.int32),expected

def slots(pool, request): request.linear_slot_idx=pool.alloc(1)[0];request.mamba_ping_pong=tuple(pool.alloc(2))
def make_req(ids,uid,table,handle,cached=0): return Req(ids.to(torch.int32),table,cached,32,uid,SamplingParams(ignore_eos=True,max_tokens=32),handle)
def forward(scheduler,request,phase,table):
    batch=Batch([request],phase)
    if phase=="prefill": batch.padded_reqs=[request];build_fla_metadata(batch,torch.device("cpu"))
    mapping=(torch.tensor([table],dtype=torch.int64),torch.tensor([request.cached_len],dtype=torch.int64))
    scheduler._forward(ForwardInput(batch,None,mapping,mapping))

def replay(*, enabled, inputs_path, raw_root, expected_commit=None):
    torch.cuda.Stream=lambda *a,**k:object();torch.cuda.set_stream=lambda *a,**k:None;torch.cuda.stream=lambda *a,**k:contextlib.nullcontext()
    old=freetoken.engine.Engine;freetoken.engine.Engine=CpuEngine
    try:
        cfg=SchedulerConfig(model_path="/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",tp_info=DistributedInfo(0,1),dtype=torch.bfloat16,cache_type="hybrid_radix",page_size=64,max_running_req=4,offline_mode=True)
        scheduler=Scheduler(cfg);scheduler.message_boundary_ckpt=enabled;cache,pool=scheduler.cache_manager,scheduler.engine.linear_state_pool
        source=source_receipt(expected_commit);donor_ids,target_ids,geometry=inputs(inputs_path,raw_root)
        donor=make_req(donor_ids,0,0,cache.match_req(SimpleNamespace(input_ids=donor_ids,input_len=len(donor_ids))).cuda_handle);slots(pool,donor);donor.message_boundary_len=BOUNDARY;donor.message_boundary_carrier=MessageBoundaryCarrier(boundary_len=BOUNDARY);cache.allocate_paged([donor]);cache.lock(donor.cache_handle)
        donor.device_len=20224;forward(scheduler,donor,"prefill",0)
        if donor.cached_len!=20224 or donor.mamba_last_track_seqlen!=NATIVE: raise RuntimeError("native 20160 track mismatch")
        cache.cache_req(donor,finished=False)
        donor.device_len=BOUNDARY;forward(scheduler,donor,"prefill",0)
        snapshot=(donor.message_boundary_carrier.snapshot_len,donor.message_boundary_carrier.snapshot_idx)
        frozen=donor.mamba_ping_pong[snapshot[1]] if snapshot[1] is not None else None
        cold=LinearStatePool(group=_group(),num_slots=4,dtype=torch.bfloat16,device=torch.device("cpu"),tp_size=1,slot_states=(SlotStateSpec("ple_conv",(4,3),layer_ids=(0,)),SlotStateSpec("ple_context",(3,),dtype=torch.int32)));cold_slot=cold.alloc(1)[0];stamp(cold,cold_slot,BOUNDARY)
        state_ok=bool(enabled and frozen is not None and torch.equal(pool.conv_states[:,frozen],cold.conv_states[:,cold_slot]) and torch.equal(pool.recurrent_states[:,frozen],cold.recurrent_states[:,cold_slot]) and all(torch.equal(pool.slot_states[k][:,frozen],cold.slot_states[k][:,cold_slot]) for k in pool.slot_states))
        donor.device_len=21302;forward(scheduler,donor,"prefill",0);cache.cache_req(donor,finished=True)
        match=cache.match_req(SimpleNamespace(input_ids=target_ids,input_len=len(target_ids)))
        expected=BOUNDARY if enabled else NATIVE
        if match.cuda_handle.cached_len!=expected: raise RuntimeError(f"admission {match.cuda_handle.cached_len} != {expected}")
        if enabled and not state_ok: raise RuntimeError("P state does not match cold reference")
        return {"schema":"d09_actual_bd57_v7_replay/v1","enabled":enabled,"target_admission_cached_tokens":match.cuda_handle.cached_len,"expected":expected,"native_track_boundary":NATIVE,"snapshot":{"length":snapshot[0],"index":snapshot[1]},"state_at_p_matches_cold_reference":state_ok,"d09_entry_created":cache._d09_entry is not None,"geometry":geometry,"source":source,"input_sha256":sha(inputs_path),"raw_pins":RAW_PINS,"model_seam":"CpuEngine.forward_batch deterministic state write + Req.complete_one only"}
    finally:
        freetoken.engine.Engine=old
        for name,value in ORIGINAL.items(): setattr(torch.cuda,name,value)

def main():
    p=argparse.ArgumentParser();p.add_argument("--raw-root",type=Path,required=True);p.add_argument("--inputs",type=Path,default=DEFAULT_INPUTS);p.add_argument("--expected-commit");p.add_argument("--enabled",action="store_true");a=p.parse_args();print(json.dumps(replay(enabled=a.enabled,inputs_path=a.inputs,raw_root=a.raw_root,expected_commit=a.expected_commit),sort_keys=True))
if __name__=="__main__":main()

