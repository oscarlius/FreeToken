"""CPU-hidden-GPU native CacheManager length replay; no length mutation after setup."""
import json, os
from types import SimpleNamespace
os.environ.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import torch
from freetoken.core import Req, SamplingParams
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
from freetoken.scheduler.cache import CacheManager

PAGE=64
def pool():
 g=LinearGatedDeltaGroupConfig(name="linear",layer_ids=(0,),num_key_heads=2,num_value_heads=4,key_head_dim=16,value_head_dim=16,conv_kernel_dim=4,output_gate="silu")
 return LinearStatePool(group=g,num_slots=16,dtype=torch.bfloat16,device=torch.device("cpu"),tp_size=1)
def slots(p,r):r.linear_slot_idx=p.alloc(1)[0];r.mamba_ping_pong=tuple(p.alloc(2))
def request(ids,uid,table,handle):
 r=Req(ids.to(torch.int32),table,0,1,uid,SamplingParams(),handle)
 r.device_len=1 # raw pre-forward state; all later transitions use complete_one.
 return r
def advance(r,boundary):
 while r.cached_len<boundary:r.complete_one()
def donor(cache,p,n,uid,table,finished=True):
 ids=torch.arange(n+1,dtype=torch.int32);match=cache.match_req(SimpleNamespace(input_ids=ids,input_len=len(ids)))
 r=request(ids,uid,table,match.cuda_handle);slots(p,r);cache.allocate_paged([r]);cache.lock(r.cache_handle);advance(r,n);cache.cache_req(r,finished=finished);return ids
def replay():
 p=pool();cache=CacheManager(1024,PAGE,torch.zeros(4,1024*PAGE,dtype=torch.int32),"hybrid_radix",linear_state_pool=p)
 d05=donor(cache,p,13376,6,0);d05_hit=cache.match_req(SimpleNamespace(input_ids=d05,input_len=len(d05))).cuda_handle.cached_len
 # Independent raw-prefix replay: generic committed donor at the observed D09 hit boundary.
 d09=donor(cache,p,20160,9,1,finished=False);d09_hit=cache.match_req(SimpleNamespace(input_ids=d09,input_len=len(d09))).cuda_handle.cached_len
 return {"d05_cached_tokens":d05_hit,"d09_cached_tokens":d09_hit,"complete_one_only":True,"cache_req_hybrid":True}
if __name__=="__main__":print(json.dumps(replay(),sort_keys=True))
