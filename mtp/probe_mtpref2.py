"""Check qwen3_next + qwen4_exp modeling for mtp handling."""
import inspect
from transformers.models.qwen3_next import modeling_qwen3_next as n3
from transformers.models.qwen4_exp import modeling_qwen4_exp as n4

for name, mod in (("qwen3_next", n3), ("qwen4_exp", n4)):
    src = inspect.getsource(mod)
    idx = [i for i in range(len(src)) if src.startswith("mtp", i)]
    print(name, "mtp occurrences:", len(idx))
    import re

    for mm in sorted(set(re.findall(r"self\.(mtp\w*|fc_\w+|pre_fc_\w+)", src))):
        print("  ", mm)
