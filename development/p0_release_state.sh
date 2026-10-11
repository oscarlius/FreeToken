set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
names=['E2-R000','E2-R003','E2-R008','E2-R009','E2-R009-p64k','E2-R006','E2-R017','E2-R011',
       'E2-pre-gate-D00','E2-pre-gate-D01','E2-pre-gate-D02','E2-R002-gate-D03','E2-R018-gate-D03',
       'E2-R001','E2-R004','E2-R005','E2-R012','E2-R014','E2-R015','E2-R016']
for name in names:
 directory=root/name; path=directory/'round.json'; doc=json.loads(path.read_text())
 history=doc.get('verdict_history',[])
 print(json.dumps({'round':name,'verdict':doc.get('verdict'),'last_verdict':history[-1] if history else None,
  'base':doc.get('base'),'experimental':doc.get('experimental'),
  'sub_conclusions':doc.get('sub_conclusions'), 'round_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
  'history_versions':len(list((directory/'round_history').glob('round.v*.json')))},ensure_ascii=False))
target=pathlib.Path('/data2/_shared/runs/ft_releases/FTD-20261004-1')
print(json.dumps({'release_dir_exists':target.exists(),'release_dir':str(target)}))
PY
