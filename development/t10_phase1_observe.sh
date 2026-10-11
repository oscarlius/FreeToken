set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json, pathlib
d = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R012')
for name in ['status_batch41.json', 'phase1_error.json', 'round_metadata.json']:
    p = d / name
    if p.is_file():
        print(name, p.read_text()[:3000])
process = pathlib.Path('/proc/2628647')
print('PID_ALIVE', process.exists() and process.joinpath('stat').read_text().partition(') ')[2][0] != 'Z')
print('BATCH_LOG_TAIL', pathlib.Path('/data2/_shared/runs/ft_rounds/batch41.log').read_text()[-4000:])
log = d / 'B1/serve.log'
if log.is_file():
    print('SERVE_LOG_TAIL', log.read_text()[-4000:])
PY
