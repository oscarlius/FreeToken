set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
from pathlib import Path
d=Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D02')
source=Path('/data2/FreeToken/runs/plan_batches/batch25_E2-pre-gate-D02_python.sh')
with (d/'batch25.sh').open('xb') as target: target.write(source.read_bytes())
print('BATCH25 WRAPPER PRESERVED')
PY
