#!/bin/bash
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1

# Clean previous test server on port 8095
fuser -k -9 8095/tcp 2>/dev/null || true
sleep 2

numactl --cpunodebind=0,1 --interleave=all \
  /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/model/Qwen3.8-Flash-Next-NVFP4-ftllm \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 \
  --host 0.0.0.0 \
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
  --reasoning-parser qwen3 > /data2/FreeToken/stage1_ftllm.log 2>&1 &

echo $!
