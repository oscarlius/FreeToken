"""Find where mtp.layers.0 attn/mlp-shared weights live."""
import safetensors

P = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/model-fp8-mtp-ple.safetensors"
attn, shared, expert_n = [], [], 0
with safetensors.safe_open(P, framework="pt", device="cpu") as f:
    for k in f.keys():
        if not k.startswith("mtp.layers.0."):
            continue
        if ".mlp.experts." in k:
            expert_n += 1
            continue
        t = f.get_tensor(k)
        row = (k, tuple(t.shape), str(t.dtype))
        if ".mlp.shared" in k or "gate" in k or "router" in k:
            shared.append(row)
        else:
            attn.append(row)
print("expert tensors:", expert_n)
print("--- shared/router ---")
for r in shared:
    print(r)
print("--- attn/other ---")
for r in attn:
    print(r)
