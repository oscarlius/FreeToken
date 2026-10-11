set -euo pipefail
git -C /data2/FreeToken/src/FreeToken bundle verify /data2/FreeToken/runs/dev_D02/d02-delivery.bundle
git -C /data2/FreeToken/src/FreeToken fetch /data2/FreeToken/runs/dev_D02/d02-delivery.bundle exp/e1-ms:exp/e1-ms
git -C /data2/FreeToken/src/FreeToken worktree add /data2/FreeToken/wt/e1ms exp/e1-ms
cp /data2/FreeToken/wt/e1r008/python/freetoken/kernel/_cpu_moe*.so /data2/FreeToken/wt/e1ms/python/freetoken/kernel/
cp /data2/FreeToken/wt/e1r008/python/freetoken/kernel/_pinned_tensor*.so /data2/FreeToken/wt/e1ms/python/freetoken/kernel/
cd /data2/FreeToken/wt/e1ms
export PYTHONPATH=python
export FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py
export PATH=/data2/FreeToken/venv/bin:/usr/local/cuda-13.0/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64:${LD_LIBRARY_PATH:-}
/data2/FreeToken/venv/bin/python -m pytest tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py tests/scheduler/test_prefill_d0_metadata.py -q | tee /data2/FreeToken/runs/dev_D02/targeted_cpu.log
