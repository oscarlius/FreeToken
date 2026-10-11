set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
base = pathlib.Path('/data2/FreeToken/runs/plan_batches')
expected = {
    'e2_launch.py': 'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf',
    'state_test_runner.py': 'bf783f25435ab2b30e9bba4c19deedd882552f146d802a829d02aa99ce8177ea',
    'state_measurement_summarize.py': 'd1c0c8bb82ab45d9a3f4339ceb592da660d6486aae600a37a22cce491de311af',
}
for name, digest in expected.items():
    if hashlib.sha256((base / name).read_bytes()).hexdigest() != digest:
        raise ValueError('reviewed T11 tool changed: ' + name)
PY
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/e2_launch.py --card T11
