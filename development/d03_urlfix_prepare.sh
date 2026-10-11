set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
p=pathlib.Path('/data2/FreeToken/runs/dev_D03/d03_gpu_selfcheck_c30ae0d_urlfix.py')
assert p.parent.is_dir() and not p.exists(), 'existing versioned runner retained'
print('URLFIX_UPLOAD_TARGET_FREE',p)
PY
