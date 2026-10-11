set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
root=pathlib.Path('/data2/FreeToken/runs/dev_D03')
for name in ['d03_phase2_launch.py','d03_t16_prepare.py','d03_t16_launch.sh']:
    assert not (root/name).exists(), name
print('D03_REVIEWED_LAUNCH_TOOL_TARGETS_FREE')
PY
