set -euo pipefail
PY=/data2/FreeToken/venv/bin/python
ROOT=/data2/FreeToken/runs/dev_D03
test "$(md5sum "$ROOT/d03_gpu_selfcheck.py" | cut -d ' ' -f 1)" = e19337d39e8c8352d1a14da5604cbf0d
test "$(md5sum "$ROOT/d03_gpu_selfcheck_2e5cdab.py" | cut -d ' ' -f 1)" = e19337d39e8c8352d1a14da5604cbf0d
test "$(md5sum "$ROOT/gate_tools_2e5cdab/t16_runner.py" | cut -d ' ' -f 1)" = e1aa92a782e731aeaad087bd5b4c4489
CUDA_VISIBLE_DEVICES='' "$PY" "$ROOT/d03_gpu_selfcheck.py" --self-test
CUDA_VISIBLE_DEVICES='' "$PY" "$ROOT/gate_tools_2e5cdab/t16_runner.py" --self-test
"$PY" -m py_compile "$ROOT/d03_gpu_selfcheck.py" "$ROOT/gate_tools_2e5cdab/t16_runner.py"
git -C /data2/FreeToken/wt/e1r003st rev-parse HEAD
md5sum "$ROOT/d03_gpu_selfcheck.py" "$ROOT/gate_tools_2e5cdab/t16_runner.py"
