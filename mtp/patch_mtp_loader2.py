"""One-shot v2: line-based gate for mtp skip. Run on server."""
import io

P = "/data2/FreeToken/src/FreeToken/python/freetoken/models/qwen4_exp/weight.py"
lines = io.open(P, encoding="utf-8").read().split("\n")
for i, ln in enumerate(lines):
    if ln == '    if raw_name.startswith("mtp."):':
        assert lines[i + 1] == "        return None", lines[i + 1]
        lines[i + 1] = (
            "        # MTP speculative head: skipped unless FT_LOAD_MTP=1 (M0 harness).\n"
            '        if os.environ.get("FT_LOAD_MTP") != "1":\n'
            "            return None\n"
            "        return raw_name"
        )
        break
else:
    raise SystemExit("anchor line missing")
io.open(P, "w", encoding="utf-8").write("\n".join(lines))
import ast

ast.parse(io.open(P, encoding="utf-8").read())
print("patched + ast OK")
