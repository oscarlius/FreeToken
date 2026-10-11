"""Extract MTP wiring from transformers qwen4_exp reference."""
import inspect
from transformers.models.qwen4_exp import modeling_qwen4_exp as m

src = inspect.getsource(m)
i = src.find("class Qwen4ExpMultiTokenPredictor")
print(src[i:i + 6000] if i >= 0 else "NO MTP CLASS")
names = [n for n in dir(m) if "mtp" in n.lower() or "multi" in n.lower() or "predictor" in n.lower()]
print("mtp-ish:", names)
