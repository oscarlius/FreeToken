set -euo pipefail
cd /data2/FreeToken/wt/e1ms
test -z "$(git status --porcelain --untracked-files=no)"
git fetch /data2/FreeToken/runs/dev_D02/d02-final.bundle exp/e1-ms
git merge --ff-only FETCH_HEAD
PYTHONPATH=python FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py /data2/FreeToken/venv/bin/python -m pytest tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py tests/scheduler/test_prefill_d0_metadata.py -q | tee /data2/FreeToken/runs/dev_D02/targeted_cpu_23f2e2c.log
test -z "$(git status --porcelain --untracked-files=no)"
test ! -e /data2/_shared/gpu.lock
ss -lntp '( sport = :8095 )'
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits
