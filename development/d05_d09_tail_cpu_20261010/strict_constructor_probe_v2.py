"""CPU-only real Scheduler constructor probe; does not execute a request."""
import contextlib
import json
import os
from types import SimpleNamespace

os.environ.update(CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
import torch
from freetoken.distributed import DistributedInfo
from freetoken.engine import Engine as RealEngine
from freetoken.kvcache.linear_state_pool import LinearStatePool
from freetoken.models.config import LinearGatedDeltaGroupConfig
import freetoken.engine
import freetoken.scheduler.scheduler as scheduler_module
from freetoken.scheduler.scheduler import Scheduler, SchedulerConfig

patched = []
original = {name: getattr(torch.cuda, name) for name in ("Stream", "set_stream", "stream")}

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
        self.kv_cache = None
        self.moe_offload_cache = None
        self.encoder_cache = None
        self.tp_cpu_group = None

def main():
    torch.cuda.Stream = lambda *a, **k: object(); patched.append("torch.cuda.Stream")
    torch.cuda.set_stream = lambda *a, **k: None; patched.append("torch.cuda.set_stream")
    torch.cuda.stream = lambda *a, **k: contextlib.nullcontext(); patched.append("torch.cuda.stream")
    old_engine = freetoken.engine.Engine
    freetoken.engine.Engine = CpuEngine
    try:
        cfg = SchedulerConfig(model_path="/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",
            tp_info=DistributedInfo(0,1), dtype=torch.bfloat16, cache_type="hybrid_radix",
            page_size=64, max_running_req=4, offline_mode=True)
        instance = Scheduler(cfg)
        print(json.dumps({"status":"constructed","patched":patched,"cache_type":instance.cache_manager.type,
            "token_pool_shape":list(instance.token_pool.shape)}))
    finally:
        freetoken.engine.Engine = old_engine
        for name, value in original.items(): setattr(torch.cuda,name,value)

if __name__ == "__main__": main()
