"""CPU-only probe: per-layer attn types + MTP template match (no weights, no GPU)."""
import sys
sys.path.insert(0, "/data2/FreeToken/src/FreeToken/python")
from freetoken.utils import cached_load_hf_config
from freetoken.models.qwen4_exp.config import parse_config

cfg = parse_config(cached_load_hf_config("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4"))
types = [cfg.attn_type_for_layer(i).name for i in range(cfg.num_layers)]
print("num_layers:", cfg.num_layers)
print("type_counts:", {t: types.count(t) for t in set(types)})
print("qsa_layers:", [i for i, t in enumerate(types) if t != "LINEAR"])
print("linear_layers:", [i for i, t in enumerate(types) if t == "LINEAR"][:40])
print("hc_count:", cfg.qwen4_args.hc_count, "hidden:", cfg.hidden_size)
