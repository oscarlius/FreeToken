set -uo pipefail
cd /data2/FreeToken/wt/e1ms
export PYTHONPATH=python
export FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py
/data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py -q > /data2/FreeToken/runs/dev_D02/cpu_regression.log 2>&1
code=$?
tail -n 42 /data2/FreeToken/runs/dev_D02/cpu_regression.log
echo "pytest_exit=$code"
exit "$code"
