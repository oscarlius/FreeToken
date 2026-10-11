"""One-shot: gate mtp.* skip in qwen4_exp/weight.py behind FT_LOAD_MTP=1. Run on server."""
import io

P = "/data2/FreeToken/src/FreeToken/python/freetoken/models/qwen4_exp/weight.py"
s = io.open(P, encoding="utf-8").read()

old_imports = "from __future__ import annotations\n\nimport json\nimport os\n"
assert old_imports in s, "imports anchor missing"

old_skip = '''def _rename(raw_name: str) -> str | None:
    """Checkpoint key -> FreeToken state-dict key, or None to skip."""
    if raw_name.startswith("mtp."):
        return None
'''
new_skip = '''_MTP_LOAD_ENV = "FT_LOAD_MTP"


def _rename(raw_name: str) -> str | None:
    """Checkpoint key -> FreeToken state-dict key, or None to skip."""
    if raw_name.startswith("mtp."):
        # MTP speculative head: skipped unless FT_LOAD_MTP=1 (M0 accept-rate
        # harness). Kept verbatim so the MTP module owns its state-dict keys.
        if os.environ.get(_MTP_LOAD_ENV) != "1":
            return None
        return raw_name
'''
assert old_skip in s, "rename anchor missing"
s = s.replace(old_skip, new_skip)
io.open(P, "w", encoding="utf-8").write(s)
print("patched _rename for FT_LOAD_MTP")
