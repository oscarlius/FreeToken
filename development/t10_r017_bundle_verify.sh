set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t10_retry_r017_8a7f9e3
cd "$target"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
expected = {
    'development/d03_t10_r017_launch.py': '8a7f9e30e60fbe66266a7b9e94f9a4fa63fa5a7b00a45704fd0d5ac6293db3e5',
    'development/t10_raw_phase1_r017.py': '13326d9ce238a5066a89cc35eb5bace1be08a9ab69767e432bd94582dfeac551',
    'development/tests/test_t10_phase1_r017.py': '2e86a71be92a6b7b1379b0083078fb78958171bb3bf67e5fa88f2d9271637102',
    'development/tests/test_t10_r017_launch.py': '0b441a808a4ab5563a2af6edad31792cf4424007fe4220bcd7611fb496363a39',
}
for name, digest in expected.items():
    path = pathlib.Path(name)
    assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
PY
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short development/tests/test_t10_phase1_r017.py development/tests/test_t10_r017_launch.py | tee regression.log
sha256sum regression.log
find "$target" -type f -exec chmod a-w {} +
find "$target" -type d -exec chmod a-w {} +
PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/t10_retry_r017_8a7f9e3')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
print('T10_R017_BUNDLE_CPU_PASS_AND_FROZEN; no GPU launch yet')
PY
