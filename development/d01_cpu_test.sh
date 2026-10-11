set -u
cd /data2/FreeToken/wt/e1r008
tar -xf /data2/FreeToken/runs/dev_D01/d01-source.tar
PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache -q > /data2/FreeToken/runs/dev_D01/pytest.log 2>&1
result=$?
tail -45 /data2/FreeToken/runs/dev_D01/pytest.log
exit "$result"
