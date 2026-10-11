set -euo pipefail
cd /data2/FreeToken/runs/plan_batches
/data2/FreeToken/venv/bin/python t03_runner.py --self-test
/data2/FreeToken/venv/bin/python t03_summarize.py --self-test
/data2/FreeToken/venv/bin/python e2_launch.py --self-test
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib
import t03_runner as runner
a=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R001/A_cut_on_p1')
records=runner.rows(a/'d0_prefill.jsonl')
tax_start=next(i for i,row in enumerate(records) if any(q['rid']==25 for q in row['reqs']))
proof=runner.validate_d0(a,1,tax_start,len(records))
print('ACTUAL RAW D02 SEMANTICS PASS',json.dumps(proof))
PY
