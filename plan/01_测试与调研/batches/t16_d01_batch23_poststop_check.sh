#!/usr/bin/env bash
set -euo pipefail
ROUND=/data2/_shared/runs/ft_rounds/E2-pre-gate-D01
printf 'batch23-processes\n'
ps -eo pid=,pgid=,args= | awk '/batch23_E2-pre-gate-D01|NEW_resume_b23|\/data2\/FreeToken\/venv\/bin\/ft serve/ && !/awk/' || true
printf 'listener-8095\n'
ss -ltnp '( sport = :8095 )' || true
printf 'gpu-mib\n'
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
printf 'lock\n'
if [[ -e "$ROUND/.gpu.lock" ]]; then cat "$ROUND/.gpu.lock"; else printf 'absent\n'; fi
printf 'new-b23-files\n'
find "$ROUND/NEW_resume_b23" -maxdepth 1 -type f -printf '%f\n' 2>/dev/null | sort || true
