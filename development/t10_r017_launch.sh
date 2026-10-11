set -euo pipefail
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib, subprocess
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/t10_retry_r017_8a7f9e3')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
launcher = root / 'development/d03_t10_r017_launch.py'
assert hashlib.sha256(launcher.read_bytes()).hexdigest() == '8a7f9e30e60fbe66266a7b9e94f9a4fa63fa5a7b00a45704fd0d5ac6293db3e5'
subprocess.run(['/data2/FreeToken/venv/bin/python', str(launcher), '--run'], check=True)
PY
