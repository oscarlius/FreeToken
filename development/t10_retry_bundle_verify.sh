set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t10_retry_r016_ready
cd "$target"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
expected = {
    'development/d03_t10_retry_launch.py': 'ec67c01f422e61dad41ca41ebe5ab4fbbd8b18ec6403c2f93a16aa0d6fa94f68',
    'development/t10_raw_phase1_retry.py': 'eda681d434ed01fa36fe58b6d049e2912895045406fdb5afff5fb9ebb02361c2',
    'development/t10_raw_phase1.py': 'b86900137665b97817d1a8e5620c2e250ef1cf61bc11698e432b6a9f75d07d52',
    'development/tests/test_t10_phase1_retry_launch.py': '97ca79f2d86ede62a4907222a3a2f54a572b31bd6c6058038d5f8037f29f5b1f',
}
for name, digest in expected.items():
    assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() == digest, name
PY
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short development/tests/test_t10_phase1_retry_launch.py | tee regression.log
sha256sum regression.log
# Freeze this newly allocated exact bundle after CPU verification.
find "$target" -type f -exec chmod a-w {} +
find "$target" -type d -exec chmod a-w {} +
PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/t10_retry_r016_ready')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
print('T10_R016_BUNDLE_CPU_PASS_AND_FROZEN; no GPU launch yet')
PY
