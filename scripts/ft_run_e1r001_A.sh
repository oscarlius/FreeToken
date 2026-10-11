#!/bin/bash
# E1-R001 组 A：分支 exp/e1r001-pr578，配置与 E1-R000 A 组一致
# 切分支 -> 起服 -> 探针 -> 跑组 -> 64K 尝试 -> 确定性对比
set -e
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

BRANCH="exp/e1r001-pr578"
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R001
mkdir -p "$ROUND_DIR"
PY=/data2/FreeToken/venv/bin/python
SC=/data2/FreeToken/scripts/ft_perf_decomp.py
GS=/data2/FreeToken/scripts/ft_run_e1r000_group.sh

echo "=== [$(date '+%H:%M:%S')] stop 8095 ==="
pkill -f "ft.distributed" 2>/dev/null || true
pkill -f "ft serve" 2>/dev/null || true
sleep 5

echo "=== checkout $BRANCH ==="
cd /data2/FreeToken/src/FreeToken
git checkout $BRANCH 2>&1 | tail -1
git rev-parse HEAD | tee "$ROUND_DIR/commit.txt"
git log --oneline -5 | tee -a "$ROUND_DIR/commit.txt"

echo '{"owner":"E1-R001-A","since":"'$(date '+%Y-%m-%d %H:%M:%S')'"}' > /data2/_shared/gpu.lock

echo "=== launch (prefill=4096 layer-major=1) ==="
GROUP=A PREFILL_LEN=4096 LAYER_MAJOR=1 ROUND=E1-R001 bash /data2/FreeToken/scripts/ft_round_e1r001_launch.sh

echo "=== wait probe ==="
for i in $(seq 1 60); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 10 -X POST http://127.0.0.1:8095/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}')
  echo "probe=$CODE at try $i"
  [ "$CODE" = "200" ] && break
  sleep 10
done
[ "$CODE" = "200" ] || { echo "PROBE FAILED"; exit 1; }

echo "=== run group A ==="
ROUND=E1-R001 bash $GS A

echo "=== 64K attempt (target 64000, may exceed kv 49152) ==="
$PY $SC run --fixture cold_long --repeat 1 --target 64000 --out "$ROUND_DIR/probe64k.jsonl" || echo "64K_ATTEMPT_EXIT=$?"

echo "=== determinism: short#0 vs short#1 completion_head ==="
$PY -c "
import json
rs=[json.loads(l) for l in open('$ROUND_DIR/groupA.jsonl')]
ss=[r for r in rs if r['label'].startswith('short')]
for r in ss: print(r['label'],'cached=',r['cached_tokens'],'head=',repr(r.get('completion_head','')[:80]))
print('DET_SHORT_EQUAL=', ss[0].get('completion_head')==ss[1].get('completion_head') if len(ss)>=2 else 'N/A')
"
echo "=== E1-R001 group A DONE ==="
