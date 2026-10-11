set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,subprocess
repo=pathlib.Path('/data2/FreeToken/wt/e1r003st')
target=pathlib.Path('/data2/FreeToken/wt/e2d03-continuation')
stage=pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_f5067bb')
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()=='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert not target.exists() and not stage.exists()
stage.mkdir()
print('D03_NEW_CANDIDATE_TARGETS_FREE; active R013 c30 tree unchanged')
PY
