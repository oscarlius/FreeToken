#!/bin/bash
# FreeToken Launch Script for Qwen3.8-Flash-Next-NVFP4 (Evaluation Run)
# Uses framework-specific overlay in /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay
# Binds to 127.0.0.1:8095

export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1

LOG_FILE="/data2/FreeToken/logs/qwen38_eval_$(date +%Y%m%d_%H%M%S).log"
mkdir -p /data2/FreeToken/logs

echo "Starting FreeToken Qwen3.8-Flash-Next server..."
echo "Log file: $LOG_FILE"

numactl --cpunodebind=0,1 --interleave=all \
  /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 \
  --host 127.0.0.1 \
  --port 8095 \
  --cors-origins '*' \
  --memory-ratio 0.88 \
  --moe-cache-auto \
  --moe-prefill-hit-d2d \
  --ple-backend pinned \
  --moe-strategy offload \
  --quant-backend moe.nvfp4=triton \
  --max-running-requests 4 \
  --cuda-graph-max-bs 4 \
  --kv-reserve-tokens 32768 \
  --max-seq-len-override 32768 \
  --max-prefill-length 4096 \
  --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > /data2/FreeToken/qwen38_eval.pid
echo "Server PID: $PID"
echo "$LOG_FILE" > /data2/FreeToken/qwen38_eval.lastlog
