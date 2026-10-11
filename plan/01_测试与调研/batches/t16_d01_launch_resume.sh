set -eu
cd /data2/FreeToken/runs/plan_batches
nohup bash batch21_E2-pre-gate-D01_resume.sh > /data2/_shared/runs/ft_rounds/batch21.log 2>&1 < /dev/null &
printf 'BATCH_PID=%s\n' "$!"
