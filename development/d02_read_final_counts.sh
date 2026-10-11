set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,re
out=pathlib.Path('/data2/FreeToken/runs/dev_D02/gpu_selfcheck_23f2e2c')
print(json.dumps({p.name:len(re.findall(r'Prefill batch,', (p/'serve.log').read_text()))
                 for p in out.iterdir() if p.is_dir()}))
PY
