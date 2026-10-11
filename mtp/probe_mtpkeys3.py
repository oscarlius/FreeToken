"""Global sweep: every mtp.* key across all shards (names only)."""
import glob
import safetensors

hits = set()
for path in sorted(glob.glob("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/*.safetensors")):
    with safetensors.safe_open(path, framework="pt", device="cpu") as f:
        for k in f.keys():
            if k.startswith("mtp."):
                s = k
                import re
                s = re.sub(r"\.mlp\.experts\.\d+", ".mlp.experts.N", s)
                s = re.sub(r"ngram_embedding\.shard_\d+", "ngram_embedding.shard_N", s)
                hits.add(s)
for k in sorted(hits):
    print(k)
