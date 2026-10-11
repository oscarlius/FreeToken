#!/bin/bash
# E1-R001 鍩虹嚎閲嶆祴鍚姩鑴氭湰锛堜笌 E0 鐢熶骇閰嶇疆瀵归綈锛歰ffload / kv路seq 49152 / 灞備紭鍏堬級
# 鏃ュ織涓?commit 鍥哄畾鍒?runs/ft_rounds/_e1/E1-R001/锛堢湅鏉垮伐浠讹級
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# 鍙樹綋鐢辩幆澧冨彉閲忔帶鍒讹細GROUP=A|B|C锛孭REFILL_LEN=4096|8192锛孡AYER_MAJOR=1|0
# A=4096+灞備紭鍏堬紙榛樿锛夛紝B=4096 闈炲眰浼樺厛锛孋=8192+灞備紭鍏?GROUP="${GROUP:-A}"
PREFILL_LEN="${PREFILL_LEN:-4096}"
LAYER_MAJOR="${LAYER_MAJOR:-1}"
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R001
mkdir -p "$ROUND_DIR"
LOG_FILE="$ROUND_DIR/serve_e1r001_$GROUP.log"

cd /data2/FreeToken/src/FreeToken
{
  echo "branch=$(git rev-parse --abbrev-ref HEAD)"
  echo "commit=$(git rev-parse HEAD)"
  echo "date=$(date '+%Y-%m-%d %H:%M:%S')"
  echo "config=offload,kv49152,seq49152,prefill${PREFILL_LEN},layer-major-${LAYER_MAJOR},mem0.88,maxreq2"
  echo "group=$GROUP"
} > "$ROUND_DIR/commit.txt"
cat "$ROUND_DIR/commit.txt"

if [ "$LAYER_MAJOR" = "1" ]; then LAYER_MAJOR_FLAG="--prefill-layer-major"; else LAYER_MAJOR_FLAG=""; fi
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
  --max-running-requests 2 \
  --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 49152 \
  --max-seq-len-override 49152 \
  --max-prefill-length $PREFILL_LEN \
  ${LAYER_MAJOR_FLAG} \
  --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 > "$LOG_FILE" 2>&1 &
echo $! > "$ROUND_DIR/serve.pid"
echo "serve pid $(cat "$ROUND_DIR/serve.pid"), log $LOG_FILE"

for i in $(seq 1 120); do
  if curl -sS -m 3 http://127.0.0.1:8095/v1/models 2>/dev/null | grep -q Qwen; then
    echo "HEALTHY at try $i ($(date '+%H:%M:%S'))"
    exit 0
  fi
  if ! kill -0 "$(cat "$ROUND_DIR/serve.pid")" 2>/dev/null; then
    echo "SERVE EXITED EARLY, tail:"
    tail -30 "$LOG_FILE"
    exit 1
  fi
  sleep 5
done
echo "TIMEOUT waiting for 8095, tail:"
tail -30 "$LOG_FILE"
exit 2
