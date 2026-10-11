set -euo pipefail
r=/data2/_shared/runs/ft_rounds/E2-R024-gate-D07
/data2/FreeToken/venv/bin/python - <<'PY'
import json,hashlib,pathlib
r=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R024-gate-D07')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
review=json.loads((r/'review_batch52.json').read_text())
round=json.loads((r/'round.json').read_text())
history=sorted((r/'round_history').glob('round.v*.json'))
print(json.dumps({'review_sha256':sha(r/'review_batch52.json'),'review_recommendation':review['recommendation'],'d0_sequence_sha256':review['d0_transfer_request_sequence_sha256'],'round_sha256':sha(r/'round.json'),'manifest_sha256':sha(r/'MANIFEST.sha256'),'round_verdict':round['verdict'],'history':[(p.name,json.loads(p.read_text()).get('verdict'),sha(p)) for p in history],'raw_hashes_unchanged':all(sha(r/k)==v for k,v in round['diagnostics']['original_raw_files'].items()),'manifest_contains_round':sha(r/'round.json') in (r/'MANIFEST.sha256').read_text()},sort_keys=True))
PY
bad=$(find "$r" -perm /0222 -print)
test -z "$bad"
stat -c '%a %u %n' "$r"