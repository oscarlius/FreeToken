"""List non-layer mtp.* keys + shapes in model-00009 (header only)."""
import safetensors

with safetensors.safe_open(
    "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4/model-00009-of-00010.safetensors",
    framework="pt",
    device="cpu",
) as f:
    for k in f.keys():
        if k.startswith("mtp.") and ".layers." not in k:
            m = f.metadata()  # noqa - unused, keep handle alive
            t = f.get_tensor(k)
            print(k, tuple(t.shape), t.dtype)
            del t
