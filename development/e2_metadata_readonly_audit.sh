set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
rows=[]
for directory in sorted(root.glob('E2-R*')):
 if directory.is_symlink() or not directory.is_dir():raise ValueError('invalid round directory')
 path=directory/'round.json'
 if not path.exists():
  rows.append({'rid':directory.name,'sealed_metadata':False});continue
 if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('not bounded regular metadata')
 raw=path.read_bytes();doc=json.loads(raw)
 rows.append({'rid':directory.name,'sealed_metadata':True,'round_sha256':hashlib.sha256(raw).hexdigest(),
  'base':doc.get('base'),'experimental':doc.get('experimental'),'parent':doc.get('parent'),
  'formal_verdict':doc.get('verdict'),'closed_at':doc.get('closed_at'),
  'history_versions':len(list((directory/'round_history').glob('round.v*.json')))})
print(json.dumps(rows))
PY
