"""All key families in mtp-ple file excluding experts + ple table."""
import struct, json
from collections import Counter

P = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/model-fp8-mtp-ple.safetensors"
with open(P, "rb") as fh:
    n = struct.unpack("<Q", fh.read(8))[0]
    hdr = json.loads(fh.read(n))
fams = Counter()
ex = Counter()
for k in hdr:
    if k == "__metadata__":
        continue
    if ".mlp.experts." in k:
        pre = k.split(".mlp.experts.")[0]
        ex[pre] += 1
        continue
    if "ngram_embedding" in k:
        fams["PLE-TABLE"] += 1
        continue
    fams[".".join(k.split(".")[:4])] += 1
print("experts by layer:", dict(ex))
print("other:")
for f_ in sorted(fams):
    print("  ", f_, fams[f_])
