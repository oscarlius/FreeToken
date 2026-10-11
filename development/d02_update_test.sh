set -euo pipefail
cd /data2/FreeToken/wt/e1ms
test -z "$(git status --porcelain --untracked-files=no)"
git fetch /data2/FreeToken/runs/dev_D02/d02-update.bundle exp/e1-ms
git merge --ff-only FETCH_HEAD
PYTHONPATH=python FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py /data2/FreeToken/venv/bin/python -m pytest tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py tests/scheduler/test_prefill_d0_metadata.py -q | tee /data2/FreeToken/runs/dev_D02/targeted_cpu_final.log
git status --short
