set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e
cd "$target"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
expected = {
 'development/d03_phase2_prepare_r017.py': 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581',
 'development/tests/test_d03_phase2_r017_prepare.py': '7d727111042fad84c4dbac785bdba4ceea0ffe9b47ecb6d136ddef48f6236b52',
 'development/d03_phase2_prepare.py': '6016c37996a3e06d78002dc688cc693cca0a39a6ff915c3ae898787e706b7b2d',
 'development/tests/test_d03_phase2_prepare.py': '46d3e67cc9a8fa0f19b2b9875367f03f5d6049f6cfad5ac0032e65c54d460894',
 'development/tests/test_d03_phase2_retry_prepare.py': '531922f5ea0e8bdb2a946722b9d616261d387ad4b1ed4e22b10725757939c9fb',
}
for name, digest in expected.items():
    path = pathlib.Path(name)
    assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
PY
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short development/tests/test_d03_phase2_prepare.py development/tests/test_d03_phase2_retry_prepare.py development/tests/test_d03_phase2_r017_prepare.py | tee regression.log
sha256sum regression.log
find "$target" -type f -exec chmod a-w {} +
find "$target" -type d -exec chmod a-w {} +
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
print('R017_METADATA_LINUX_CPU_VERIFIED_AND_FROZEN')
PY
