"""Probe: transformers availability + qwen3_next MTP reference."""
import importlib.util

print("transformers:", importlib.util.find_spec("transformers") is not None)
try:
    import transformers

    print("version:", transformers.__version__)
    from transformers import models

    names = [n for n in dir(models) if "qwen3" in n.lower() or "qwen4" in n.lower()]
    print("qwen models:", names)
except Exception as e:
    print("err:", type(e).__name__, str(e)[:200])
