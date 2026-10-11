set -euo pipefail
cd /data2/FreeToken/runs/plan_batches
nohup bash batch22_E2-pre-gate-D01_resume_fixed.sh > /data2/_shared/runs/ft_rounds/batch22.log 2>&1 < /dev/null &
printf 'BATCH_PID=%s\n' "$!"
