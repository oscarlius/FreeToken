set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,runpy
m=runpy.run_path('/data2/FreeToken/runs/plan_batches/t16_runner.py')
parse=runpy.run_path('/data2/FreeToken/scripts/serve_args_diff.py')['parse']
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D01')
a,b=d/'PARENT',d/'NEW_b24'
args=m['strict_args'](parse(str(a/'serve.log')),parse(str(b/'serve.log')),{'prefill_anchor_cut':'True'})
det=m['check_det']([a/'det.json',b/'det.json'],32052,128)
if (a/'prefill_seq.txt').read_bytes()!=(b/'prefill_seq.txt').read_bytes(): raise SystemExit('BUSINESS SEQ DIFF')
prefill=m['check_prefill'](a,b,False)
print(json.dumps({'args':args,'det':det,'prefill':prefill},ensure_ascii=False))
PY
