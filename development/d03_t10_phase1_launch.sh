set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib, subprocess
path = pathlib.Path('/data2/FreeToken/runs/dev_D03/d03_phase2_launch.py')
assert hashlib.sha256(path.read_bytes()).hexdigest() == '6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe'
# The actual producer selects its GPU and takes the shared atomic lock.
subprocess.run(['/data2/FreeToken/venv/bin/python', str(path), '--card', 'T10-P1', '--run'], check=True)
PY
