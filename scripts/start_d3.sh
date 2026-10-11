#!/bin/bash
# D3 多锚检查点：生产参数 + 层优先预填 + 特殊 token 检查点
# 与 runs/dev_d1/serve_final.log 的参数完全一致（窗口三件套 49152）
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

LOG=${1:-/data2/FreeToken/runs/dev_d3/serve_d3.log}
mkdir -p "$(dirname "$LOG")"

numactl --cpunodebind=0,1 --interleave=all \
  /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 \
  --host 0.0.0.0 \
  --port 8095 \
  --memory-ratio 0.88 \
  --moe-cache-auto \
  --moe-prefill-hit-d2d \
  --ple-backend pinned \
  --moe-strategy offload \
  --quant-backend moe.nvfp4=triton \
  --max-running-requests 2 \
  --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 49152 \
  --max-seq-len-override 49152 \
  --max-prefill-length 4096 \
  --prefill-layer-major \
  --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 > "$LOG" 2>&1 &

echo $! > /data2/FreeToken/qwen38_d3.pid
echo "pid $(cat /data2/FreeToken/qwen38_d3.pid) log $LOG"
