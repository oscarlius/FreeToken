#!/bin/bash
cd /data2/_shared/runs/ft_rounds/E1-R003 || exit 1
for f in warm cold lm; do
  echo "$f $(grep -c 'Prefill batch' $f/serve.log) mtime=$(stat -c %y $f/serve.log | cut -c12-19)"
done
/data2/FreeToken/venv/bin/python - << 'PY'
import json
d=json.load(open("replay_warm.json"))
R=d.get("rounds", d) if isinstance(d, dict) else d
print(type(R).__name__, len(R) if hasattr(R, "__len__") else "na")
if isinstance(d, dict):
    print("KEYS", list(d.keys())[:30])
rows = R if isinstance(R, list) else []
print("NROWS", len(rows))
if rows:
    print("ROWKEYS", list(rows[0].keys())[:40])
for i, x in enumerate(rows):
    if not isinstance(x, dict):
        print("ROW", i, type(x).__name__)
        continue
    keep = {k: x.get(k) for k in ("idx","round","prompt_tokens","cached_tokens","recomputed_tokens","ttft_any_s","ttft_s","ttft_first_real_s") if k in x or True}
    # also print any key containing ttft or recompute
    extra = {k: x[k] for k in x if "ttft" in k or "recomp" in k or k in ("idx","round","i")}
    print(i, extra)
PY
