set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
base = pathlib.Path('/data2/FreeToken/runs/dev_D03')
tools = base / 't04_retry_r015_ready'
close = base / 'phase2_close_6016c37'
assert not tools.exists() and not close.exists()
scripts = pathlib.Path('/data2/FreeToken/scripts')
expected = {'round_json_append.py': '88178a9a3c83dec204e90e6dcf8c4db9',
            'round_close.py': '415aa82b34c8fd82d09bfe8a8ce67eed',
            'round_close.sh': '430693122ef66bb5a293fb421ff0f7fc'}
for name, digest in expected.items():
    assert hashlib.md5((scripts / name).read_bytes()).hexdigest() == digest, name
for root in [tools, close]:
    root.mkdir()
    (root / 'development/tests').mkdir(parents=True)
(tools / 'development/e2d03/scripts').mkdir(parents=True)
(close / 'scripts').mkdir()
for name in expected:
    with (close / 'scripts' / name).open('xb') as stream:
        stream.write((scripts / name).read_bytes())
print('R015 tooling and metadata candidate bundles prepared; not GPU launch')
PY
