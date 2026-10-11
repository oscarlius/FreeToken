"""Verify FT_LOAD_MTP gate on branch code."""
import os
import freetoken.models.qwen4_exp.weight as w

print("module:", w.__file__)
assert "src/FreeToken" in w.__file__, "not branch code!"
assert w._rename("mtp.fc_embedding.weight") is None, "default must skip"
os.environ["FT_LOAD_MTP"] = "1"
assert w._rename("mtp.fc_embedding.weight") == "mtp.fc_embedding.weight"
assert w._rename("mtp.layers.0.attn.qkv.weight") == "mtp.layers.0.attn.qkv.weight"
del os.environ["FT_LOAD_MTP"]
assert w._rename("model.layers.0.attn.qkv.weight") == "model.layers.0.attn.qkv.weight"
print("MTP gate OK")
