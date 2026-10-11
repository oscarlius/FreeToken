set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/candidate_0369263')
target=pathlib.Path('/data2/FreeToken/wt/e2d06')
assert not stage.exists(), 'candidate stage already exists; inspect before any retry'
assert not target.exists(), 'candidate tree already exists; inspect instead of replacing'
stage.mkdir()
print(str(stage))
PY
