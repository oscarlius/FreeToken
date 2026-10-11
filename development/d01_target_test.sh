set -u
cd /data2/FreeToken/wt/e1r008
tar -xf /data2/FreeToken/runs/dev_D01/d01-source.tar
PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest tests/scheduler/test_switch_defaults.py tests/scheduler/test_prefill_anchor_cut_switch.py tests/scheduler/test_prefill_d0_metadata.py tests/scheduler/test_anchor_cut_scheduler_wiring.py tests/scheduler/test_hybrid_cache_manager.py -q > /data2/FreeToken/runs/dev_D01/targeted_pytest.log 2>&1
result=$?
cat /data2/FreeToken/runs/dev_D01/targeted_pytest.log
exit "$result"
