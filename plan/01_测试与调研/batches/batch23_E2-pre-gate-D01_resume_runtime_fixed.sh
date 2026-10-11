#!/bin/bash
set -euo pipefail

RID=E2-pre-gate-D01
D=/data2/_shared/runs/ft_rounds/$RID
PY=/data2/FreeToken/venv/bin/python
FT=/data2/FreeToken/venv/bin/ft
SCR=/data2/FreeToken/scripts
SOURCE=/data2/FreeToken/runs/plan_batches/batch22_E2-pre-gate-D01_resume_fixed.sh

export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64:${LD_LIBRARY_PATH:-}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1

echo "### $RID T16 batch23 start $(date '+%F %T')"
test -d "$D"
test -s "$D/PARENT/det.json"
test ! -e "$D/NEW_resume_b23"
test ! -e "$D/PARENT_P"
test ! -e "$D/NEW_P"
cp "$0" "$D/batch23.sh"

echo "PREFLIGHT PATH=$PATH"
echo "PREFLIGHT LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
test "$(command -v ft)" = "$FT"
test "$(readlink -f "$(command -v ft)")" = "$FT"
"$FT" --help > "$D/batch23_ft_help.txt"
numactl --cpunodebind=0,1 --interleave=all "$FT" --help > "$D/batch23_numactl_ft_help.txt"
PYTHONPATH=/data2/FreeToken/wt/e1r008/python "$PY" -c 'import freetoken.kernel._pinned_tensor,freetoken.kernel._cpu_moe;print("extensions-ok")' > "$D/batch23_extensions.txt"
sha256sum "$SCR/cold_eq.py" "$SCR/ft_probe_ckpt_tax.py" "$SCR/serve_args_diff.py" > "$D/batch23_tools.sha256"
grep -F 'set -euo pipefail' "$SOURCE" > /dev/null
grep -F 'COLD_ID=E2-pre-gate-D01-det' "$SOURCE" > /dev/null
grep -F "re.fullmatch(r'\\.pid=\\d+'" "$SOURCE" > /dev/null
grep -F 'strict_h2d' "$SOURCE" > /dev/null

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
sed \
  -e 's/NEW_resume/NEW_resume_b23/g' \
  -e 's/batch22/batch23/g' \
  -e 's#ft serve#/data2/FreeToken/venv/bin/ft serve#g' \
  "$SOURCE" > "$tmp"
bash -n "$tmp"
echo 'PREFLIGHT-OK runtime,exports,ft,numactl,extensions,tools,strict-helpers'
bash "$tmp"
"$PY" - "$D/PARENT/det.json" "$D/NEW_resume_b23/det.json" "$D/PARENT_P/det.json" "$D/NEW_P/det.json" <<'PY'
import json, sys
records = [json.load(open(path)) for path in sys.argv[1:]]
inputs = [record['record'] for record in records]
fields = ('cold_id', 'built_tokens', 'prompt_tokens', 'cached_tokens')
values = [tuple(item.get(field) for field in fields) for item in inputs]
if len(set(values)) != 1:
    raise SystemExit('DET INPUT DIFF ' + repr(values))
for item, record in zip(inputs, records):
    if item.get('built_tokens') != 32052 or item.get('completion_tokens') != 128:
        raise SystemExit('DET TOKEN CONTRACT ' + repr(item))
    if not item.get('prompt_tokens', 0) or abs(item['prompt_tokens'] - 32064) >= 2000:
        raise SystemExit('DET PROMPT CONTRACT ' + repr(item))
    if item.get('cached_tokens') != 0 or not record.get('events'):
        raise SystemExit('DET COLD OR EVENTS CONTRACT ' + repr(item))
print('DET INPUT FAILCLOSE OK ' + repr(values[0]))
PY
