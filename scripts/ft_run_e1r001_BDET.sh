#!/bin/bash
# E1-R001 后续：B 组（4096 非层优先）-> 回 A 配置 -> 确定性对子（seed7：PR vs base）
set -e
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data2/FreeToken/venv/bin/python
SC=/data2/FreeToken/scripts/ft_perf_decomp.py
GS=/data2/FreeToken/scripts/ft_run_e1r000_group.sh
LA=/data2/FreeToken/scripts/ft_round_e1r001_launch.sh
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R001

wait_probe() {
  for i in $(seq 1 60); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 10 -X POST http://127.0.0.1:8095/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}')
    [ "$CODE" = "200" ] && echo "READY at try $i" && return 0
    sleep 10
  done
  echo "PROBE FAILED"; return 1
}
stop_serve() {
  pkill -f "ft.distributed" 2>/dev/null || true
  pkill -f "ft serve" 2>/dev/null || true
  sleep 5
}

echo "=== [$(date '+%H:%M:%S')] B: restart LAYER_MAJOR=0 ==="
stop_serve
GROUP=B PREFILL_LEN=4096 LAYER_MAJOR=0 bash $LA
wait_probe
ROUND=E1-R001 bash $GS B

echo "=== [$(date '+%H:%M:%S')] DET-PR: restart A config, seed7 ==="
stop_serve
GROUP=DETPR PREFILL_LEN=4096 LAYER_MAJOR=1 bash $LA
wait_probe
$PY $SC run --fixture cold_long --repeat 1 --target 32000 --seed 7 --out "$ROUND_DIR/det_pr.jsonl"

echo "=== [$(date '+%H:%M:%S')] DET-BASE: checkout dev/d-series-clean, restart A, seed7 ==="
stop_serve
cd /data2/FreeToken/src/FreeToken
git checkout dev/d-series-clean 2>&1 | tail -1
git rev-parse HEAD | tee -a "$ROUND_DIR/commit.txt"
GROUP=DETBASE PREFILL_LEN=4096 LAYER_MAJOR=1 bash $LA
wait_probe
$PY $SC run --fixture cold_long --repeat 1 --target 32000 --seed 7 --out "$ROUND_DIR/det_base.jsonl"

echo "=== determinism compare (full text) ==="
$PY -c "
import json
pr=json.loads(open('$ROUND_DIR/det_pr.jsonl').read().strip().splitlines()[-1])
ba=json.loads(open('$ROUND_DIR/det_base.jsonl').read().strip().splitlines()[-1])
print('PR   ttft=',pr['ttft_s'],'decode=',pr['decode_tps'])
print('BASE ttft=',ba['ttft_s'],'decode=',ba['decode_tps'])
print('DET_FULL_EQUAL=', pr.get('completion_text')==ba.get('completion_text'))
print('PR prompt=',pr['prompt_tokens'],'BASE prompt=',ba['prompt_tokens'])
"
echo "=== E1-R001 B+DET DONE ==="
