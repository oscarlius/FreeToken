set -euo pipefail
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib, subprocess, os
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/t10_retry_r016_ready')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
launcher = root / 'development/d03_t10_retry_launch.py'
assert hashlib.sha256(launcher.read_bytes()).hexdigest() == 'ec67c01f422e61dad41ca41ebe5ab4fbbd8b18ec6403c2f93a16aa0d6fa94f68'
assert os.environ['CUDA_VISIBLE_DEVICES'] == '0'
subprocess.run(['/data2/FreeToken/venv/bin/python', str(launcher), '--run'], check=True)
PY
