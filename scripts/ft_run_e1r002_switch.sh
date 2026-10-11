#!/bin/bash
# E1-R002 单变体全流程：停服 -> 指定策略重启 -> 探针 -> P0组 -> 60题质量
# 用法：ft_run_e1r002_switch.sh <GROUP> <STRATEGY> <FETCH>
#   GROUP=A offload对照 / GROUP=B hybrid默认 / GROUP=C hybrid调大fetch
set -e
GROUP="$1"
STRATEGY="$2"
FETCH="$3"
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R002
mkdir -p "$ROUND_DIR"
echo "=== [$(date '+%H:%M:%S')] stop current serve ==="
bash /data2/FreeToken/scripts/ft_serve_stop.sh "$ROUND_DIR" || true
echo "=== [$(date '+%H:%M:%S')] launch group $GROUP ($STRATEGY fetch=$FETCH) ==="
GROUP="$GROUP" MOE_STRATEGY="$STRATEGY" HYBRID_MAX_FETCH="$FETCH" \
  bash /data2/FreeToken/scripts/ft_round_e1r002_launch.sh
echo "=== [$(date '+%H:%M:%S')] probe + P0 group $GROUP ==="
for i in $(seq 1 40); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 30 -X POST http://127.0.0.1:8095/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"temperature":0,"stream":false}' || echo 000)
  if [ "$CODE" = "200" ]; then echo "READY probe=200 at try $i"; break; fi
  echo "probe=$CODE at try $i"
  sleep 10
done
bash /data2/FreeToken/scripts/ft_run_group2.sh "$ROUND_DIR" "$GROUP"
echo "=== [$(date '+%H:%M:%S')] quality60 group $GROUP ==="
FT_RUN_DIR="$ROUND_DIR/quality_$GROUP" FT_API_BASE=http://127.0.0.1:8095/v1 \
  /data2/FreeToken/venv/bin/python /data2/_shared/benchmark_client.py phase3 \
  Qwen3.8-Flash-Next-NVFP4 /data2/_shared/test_prompts_60.json \
  > "$ROUND_DIR/quality_${GROUP}.log" 2>&1
echo "=== [$(date '+%H:%M:%S')] group $GROUP DONE ==="
