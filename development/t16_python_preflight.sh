set -euo pipefail
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/t16_runner.py --self-test
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/t16_runner.py --gate D01 --rid E2-pre-gate-D01 --batch 24
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,re
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D01/PARENT')
data=json.loads((d/'det.json').read_text())
assert data['record']['cold_id']=='E2-pre-gate-D01-det'
assert data['record']['cached_tokens']==0 and data['record']['prompt_tokens']==32064
all_events=re.findall(r'#new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)', (d/'serve.log').read_text())
rows=[json.loads(x) for x in (d/'d0_prefill.jsonl').read_text().splitlines()]
assert len(all_events)-1==len(rows),(len(all_events),len(rows))
assert not pathlib.Path('/data2/_shared/runs/ft_rounds/batch24.log').exists()
print(json.dumps({'parent_events':len(all_events),'parent_rows':len(rows),
                  'parent_det':data['record'],
                  'runner_md5':hashlib.md5(pathlib.Path('/data2/FreeToken/runs/plan_batches/t16_runner.py').read_bytes()).hexdigest()}))
PY
