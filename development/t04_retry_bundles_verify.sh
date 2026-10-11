set -euo pipefail
tools=/data2/FreeToken/runs/dev_D03/t04_retry_r015_ready
close=/data2/FreeToken/runs/dev_D03/phase2_close_6016c37
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
base = pathlib.Path('/data2/FreeToken/runs/dev_D03')
expected = {
 't04_retry_r015_ready/development/d03_t04_retry_launch.py': '671b8aa22fb0722331b306ccd75f5085f8d9f4e70bb96226374217de442a6423',
 't04_retry_r015_ready/development/t04_logits_retry.py': '7358a1fffa012a6fcd47a5c15e027fbddab6994abe7bb47fadb28f4cb3bf3b9f',
 't04_retry_r015_ready/development/t04_capture_controlled.py': 'b7d6054237fac0efb4e575fcdb746318fa971337b7e83e8e34b5b1e13bbc0237',
 't04_retry_r015_ready/development/t04_logits_phase2.py': 'd7226c466e5922ecc4e80d80dc2b634592e1449538587d3232d4f3b9176723eb',
 't04_retry_r015_ready/development/d03_phase2_launch.py': '6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe',
 't04_retry_r015_ready/development/e2d03/scripts/logits_probe.py': '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7',
 't04_retry_r015_ready/development/tests/test_t04_capture_controlled.py': 'aff7f8c97ef37ef7810c655f84cb215bed0dab29ae9c969a75baeb1411640983',
 't04_retry_r015_ready/development/tests/test_t04_logits_retry.py': '1c915919ebfa26416bfff4ce19e39f81ab4f3a684c256b99e909b745194273dd',
 't04_retry_r015_ready/development/tests/test_d03_t04_retry_launch.py': '8526f464aac8a2e3d14fc69007201be5851f3be433eeabfaa244041b95320fa7',
 'phase2_close_6016c37/development/d03_phase2_prepare.py': '6016c37996a3e06d78002dc688cc693cca0a39a6ff915c3ae898787e706b7b2d',
 'phase2_close_6016c37/development/tests/test_d03_phase2_prepare.py': '46d3e67cc9a8fa0f19b2b9875367f03f5d6049f6cfad5ac0032e65c54d460894',
 'phase2_close_6016c37/development/tests/test_d03_phase2_retry_prepare.py': '531922f5ea0e8bdb2a946722b9d616261d387ad4b1ed4e22b10725757939c9fb',
}
for name, digest in expected.items():
    assert hashlib.sha256((base / name).read_bytes()).hexdigest() == digest, name
PY
cd "$tools"
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short development/tests/test_t04_capture_controlled.py development/tests/test_t04_logits_retry.py development/tests/test_d03_t04_retry_launch.py | tee regression.log
cd "$close"
PYTHONDONTWRITEBYTECODE=1 CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short development/tests/test_d03_phase2_prepare.py development/tests/test_d03_phase2_retry_prepare.py | tee regression.log
sha256sum "$tools/regression.log" "$close/regression.log"
find "$tools" "$close" -type f -exec chmod a-w {} +
find "$tools" "$close" -type d -exec chmod a-w {} +
PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
base = pathlib.Path('/data2/FreeToken/runs/dev_D03')
for name in ['t04_retry_r015_ready', 'phase2_close_6016c37']:
    root = base / name
    assert all(not p.is_symlink() and not p.stat().st_mode & 0o222 for p in [root, *root.rglob('*')])
print('R015_TOOLING_AND_RETRY_METADATA_LINUX_CPU_VERIFIED_FROZEN; GPU not launched')
PY
