set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t04_retry_r015_71d4846
cd "$target"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
expected = {
 'development/d03_t04_retry_launch.py': '71d4846071762613989b22cfa76e52b6cbdf18e6ef7b4463aa8145d2b734a5d1',
 'development/t04_logits_retry.py': '1f8dcac3f75bcd98b38b496068e727d13435cdf60117f0d99c27b95370445458',
 'development/t04_capture_controlled.py': '14b1eb09a9a49ba4c46176ca3edc5d52b927a07f4c476ae55c1d144c979c50fb',
 'development/t04_logits_phase2.py': 'd7226c466e5922ecc4e80d80dc2b634592e1449538587d3232d4f3b9176723eb',
 'development/d03_phase2_launch.py': '6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe',
 'development/e2d03/scripts/logits_probe.py': '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7',
 'development/tests/test_t04_capture_controlled.py': '040fe9376cbfffd8e8c07ba02b6df00b5d374d15b7a24c50ee7103d642a7cda2',
 'development/tests/test_t04_logits_retry.py': '1c915919ebfa26416bfff4ce19e39f81ab4f3a684c256b99e909b745194273dd',
 'development/tests/test_d03_t04_retry_launch.py': '8526f464aac8a2e3d14fc69007201be5851f3be433eeabfaa244041b95320fa7',
}
for name, digest in expected.items():
    assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() == digest, name
PY
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short development/tests/test_t04_capture_controlled.py development/tests/test_t04_logits_retry.py development/tests/test_d03_t04_retry_launch.py | tee regression.log
sha256sum regression.log
find "$target" -type f -exec chmod a-w {} +
find "$target" -type d -exec chmod a-w {} +
PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/t04_retry_r015_71d4846')
assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
print('FINAL_R015_RETRY_LINUX_CPU_PASS_AND_FROZEN; no GPU launch')
PY
