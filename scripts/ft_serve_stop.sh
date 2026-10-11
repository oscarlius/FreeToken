#!/usr/bin/env bash
# 通用停服：kill -> 等进程消失 -> 等显存释放 (<2GB, 最长 180s)
# 用法：ft_serve_stop.sh <ROUND_DIR>
set -e
ROUND_DIR="$1"
if [ -f "$ROUND_DIR/serve.pid" ]; then
  PID=$(cat "$ROUND_DIR/serve.pid")
  kill "$PID" 2>/dev/null || true
  for i in $(seq 1 30); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 2
  done
  kill -0 "$PID" 2>/dev/null && { echo "WARN: pid $PID still alive, pkill -9"; pkill -9 -f "port 8095" 2>/dev/null || true; sleep 3; }
fi
pkill -f "ft serve" 2>/dev/null || true
sleep 3
for i in $(seq 1 36); do
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  echo "gpu_used=${USED}MiB (wait $i)"
  [ "$USED" -lt 2000 ] && { echo "GPU_FREE"; exit 0; }
  sleep 5
done
echo "GPU_NOT_FREE_TIMEOUT"
exit 1
