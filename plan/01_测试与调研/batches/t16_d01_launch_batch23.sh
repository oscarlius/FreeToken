set -euo pipefail
cd /data2/FreeToken/runs/plan_batches
nohup bash batch23_E2-pre-gate-D01_resume_runtime_fixed.sh > /data2/_shared/runs/ft_rounds/batch23.log 2>&1 < /dev/null &
printf 'BATCH_PID=%s\n' "$!"
