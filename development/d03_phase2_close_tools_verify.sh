set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/phase2_close_24e8656
cd "$target"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
expected = {
    'development/d03_phase2_prepare.py': '24e8656380890c0eb04b3ee67c52b8c32525c8a96ad93fc0f5f4d9cc1d6f9d50',
    'development/tests/test_d03_phase2_prepare.py': '46d3e67cc9a8fa0f19b2b9875367f03f5d6049f6cfad5ac0032e65c54d460894',
}
for name, digest in expected.items():
    assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() == digest, name
assert hashlib.md5(pathlib.Path('scripts/round_json_append.py').read_bytes()).hexdigest() == '88178a9a3c83dec204e90e6dcf8c4db9'
PY
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q --tb=short development/tests/test_d03_phase2_prepare.py | tee regression.log
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m py_compile development/d03_phase2_prepare.py
test ! -e /data2/FreeToken/runs/dev_D03/d03_phase2_prepare.py
cp --no-clobber development/d03_phase2_prepare.py /data2/FreeToken/runs/dev_D03/d03_phase2_prepare.py
cmp development/d03_phase2_prepare.py /data2/FreeToken/runs/dev_D03/d03_phase2_prepare.py
sha256sum development/d03_phase2_prepare.py development/tests/test_d03_phase2_prepare.py regression.log
