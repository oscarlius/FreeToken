set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
base = pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_close_6016c37')
target = pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e')
assert not target.exists()
expected = {
    'development/d03_phase2_prepare.py': '6016c37996a3e06d78002dc688cc693cca0a39a6ff915c3ae898787e706b7b2d',
    'development/tests/test_d03_phase2_prepare.py': '46d3e67cc9a8fa0f19b2b9875367f03f5d6049f6cfad5ac0032e65c54d460894',
    'development/tests/test_d03_phase2_retry_prepare.py': '531922f5ea0e8bdb2a946722b9d616261d387ad4b1ed4e22b10725757939c9fb',
    'scripts/round_json_append.py': 'a4bd8b095bf718076f4d4b7f9ed8d6f5a96263b80e455ae2324d4f3c67601c91',
    'scripts/round_close.py': 'e6fa3bc840c5c6e7c5fa43d4091bb5011932e6f856c2e0111ecdbe590f730c08',
    'scripts/round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9',
}
for name, digest in expected.items():
    path = base / name
    assert not path.is_symlink() and not path.stat().st_mode & 0o222
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
target.mkdir()
for name in expected:
    path = target / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write((base / name).read_bytes())
print('R017_METADATA_BUNDLE_ALLOCATED; old helper remains unchanged')
PY
