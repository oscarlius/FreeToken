set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
print(json.dumps([{'rid':p.name,'closed':(p/'MANIFEST.sha256').exists(),
 'status':[json.loads(x.read_text()) for x in p.glob('status_batch*.json')]}
 for p in sorted(root.iterdir()) if p.is_dir() and any(k in p.name for k in ('D06','D07','D14','T17'))],indent=2))
lock=pathlib.Path('/data2/_shared/gpu.lock')
print('LOCK',lock.read_text() if lock.exists() else 'absent')
print(subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True))
PY
