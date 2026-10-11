set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
out=pathlib.Path('/data2/FreeToken/runs/dev_D03/phase2_tools_c30ae0d')
assert out.parent.is_dir() and not out.exists(), 'existing helper delivery retained; do not overwrite'
out.mkdir();(out/'tests').mkdir()
print('PHASE2_TOOL_STAGE_CREATED',out)
PY
