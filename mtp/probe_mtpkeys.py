"""List distinct mtp.* key shapes (header-only) from model-00009 + mtp-ple file."""
import json
import safetensors

files = [
    "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/model-00009-of-00010.safetensors",
    "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/model-fp8-mtp-ple.safetensors",
]
seen = {}
for path in files:
    with safetensors.safe_open(path, framework="pt", device="cpu") as f:
        for k in f.keys():
            if k.startswith("mtp.") and ".mlp.experts." not in k:
                if k not in seen:
                    t = f.get_tensor(k)
                    seen[k] = (tuple(t.shape), str(t.dtype))
for k in sorted(seen):
    print(k, seen[k])
print("n_mtp_dense_keys", len(seen))
