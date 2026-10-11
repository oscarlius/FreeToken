set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
for rid in ['E2-base','E2-pre','E2-pre-gate-D00','E2-R018-gate-D03']:
 p=root/rid/'round.json'
 if p.is_file():
  d=json.loads(p.read_text());print(json.dumps({'rid':rid,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'round_id':d.get('round_id'),'base':d.get('base'),'closed_at':d.get('closed_at')}))
 else:print(json.dumps({'rid':rid,'exists':False}))
p=pathlib.Path('/data2/FreeToken/wt/e2d03-continuation/scripts/logits_probe.py')
print(json.dumps({'candidate_probe_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
PY
