set -euo pipefail
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib, subprocess
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/t04_retry_r015_71d4846')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
launcher = root / 'development/d03_t04_retry_launch.py'
assert hashlib.sha256(launcher.read_bytes()).hexdigest() == '71d4846071762613989b22cfa76e52b6cbdf18e6ef7b4463aa8145d2b734a5d1'
subprocess.run(['/data2/FreeToken/venv/bin/python', str(launcher), '--run'], check=True)
PY
