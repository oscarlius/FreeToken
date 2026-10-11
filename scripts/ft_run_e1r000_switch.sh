#!/usr/bin/env bash
# E1-R000 B/C 组：重启服务（换变体）-> 等探针 -> 跑同组测试
# 用法：switch_group.sh B  (PREFILL_LEN/LAYER_MAJOR 由组决定)
set -e
GROUP="$1"
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R000
if [ "$GROUP" = "B" ]; then
  export PREFILL_LEN=4096 LAYER_MAJOR=0
elif [ "$GROUP" = "C" ]; then
  export PREFILL_LEN=8192 LAYER_MAJOR=1
else
  echo "unknown group $GROUP"; exit 2
fi
export GROUP
echo "=== [$(date '+%H:%M:%S')] stop current serve ==="
if [ -f "$ROUND_DIR/serve.pid" ]; then
  kill "$(cat "$ROUND_DIR/serve.pid")" 2>/dev/null || true
  sleep 8
fi
echo "=== [$(date '+%H:%M:%S')] launch group $GROUP (prefill=$PREFILL_LEN layer-major=$LAYER_MAJOR) ==="
bash /data2/FreeToken/scripts/ft_round_e1r000_launch.sh
echo "=== [$(date '+%H:%M:%S')] wait probe + run group $GROUP ==="
bash /data2/FreeToken/scripts/ft_run_e1r000_ready.sh "$GROUP"
echo "=== [$(date '+%H:%M:%S')] group $GROUP DONE ==="
