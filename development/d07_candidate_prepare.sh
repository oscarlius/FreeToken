set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
from pathlib import Path
stage = Path('/data2/FreeToken/runs/dev_D07/candidate_fefb19c')
target = Path('/data2/FreeToken/wt/e2d07')
if stage.exists() or stage.is_symlink() or target.exists() or target.is_symlink():
    raise ValueError('candidate stage or worktree already exists; inspect rather than overwrite')
stage.mkdir()
print(stage)
PY
