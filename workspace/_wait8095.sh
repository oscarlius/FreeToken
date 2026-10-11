#!/bin/bash
set -u
for i in $(seq 1 40); do
  body=$(curl -sS -m 3 http://127.0.0.1:8095/health 2>/dev/null || true)
  echo "try=$i ${body:-DOWN}"
  case "$body" in
    *'"status":"ok"'*) echo READY; nvidia-smi --query-gpu=memory.used,memory.free --format=csv; exit 0 ;;
  esac
  if ! pgrep -f '/home/dell/.local/bin/ft serve' >/dev/null; then
    echo DIED
    tail -n 40 /data2/FreeToken/experiments/perf-20260928-1245/restore-8095.log
    exit 1
  fi
  sleep 15
done
echo TIMEOUT
tail -n 30 /data2/FreeToken/experiments/perf-20260928-1245/restore-8095.log
exit 1
