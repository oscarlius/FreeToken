#!/usr/bin/env bash
# E1-R001 确定性门 DET-PR + DET-BASE（seed7 同提示全文对比）
# 流程：停服 -> PR分支A配置跑seed7 -> 停服 -> 切base(3c8f224)跑seed7 -> 切回PR分支 -> 对比
set -e
SRC=/data2/FreeToken/src/FreeToken
SCR=/data2/FreeToken/scripts
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/E1-R001
PY=/data2/FreeToken/venv/bin/python
SC=$SCR/ft_perf_decomp.py
PR_BRANCH=exp/e1r001-pr578
BASE_COMMIT=3c8f2241f8f0b462071bb1576086f32135cec7ad

restore_branch() {
  cd $SRC
  git checkout $PR_BRANCH 2>&1 | tail -1
  echo "restored branch: $(git rev-parse --abbrev-ref HEAD) $(git rev-parse --short HEAD)"
}
trap restore_branch EXIT

echo '{"owner":"E1-R001-DET","since":"'$(date '+%Y-%m-%d %H:%M:%S')'"}' > /data2/_shared/gpu.lock

run_seed7() {
  local OUT="$1"
  for i in $(seq 1 40); do
    CODE=$(curl -s -o /dev/null -m 10 -X POST http://127.0.0.1:8095/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' -w "%{http_code}")
    [ "$CODE" = "200" ] && { echo "READY at try $i"; break; }
    echo "probe=$CODE at try $i"
    sleep 10
  done
  [ "$CODE" = "200" ] || { echo "PROBE FAILED"; exit 1; }
  $PY $SC run --fixture cold_long --repeat 1 --target 32000 --seed 7 --out "$OUT" | tail -12
}

echo "=== [$(date '+%H:%M:%S')] DET-PR (branch $PR_BRANCH) ==="
cd $SRC && git checkout $PR_BRANCH 2>&1 | tail -1
bash $SCR/ft_serve_stop.sh "$ROUND_DIR"
GROUP=DETPR PREFILL_LEN=4096 LAYER_MAJOR=1 bash $SCR/ft_round_e1r001_launch.sh
run_seed7 "$ROUND_DIR/det_pr.jsonl"

echo "=== [$(date '+%H:%M:%S')] DET-BASE (detached $BASE_COMMIT) ==="
bash $SCR/ft_serve_stop.sh "$ROUND_DIR"
cd $SRC && git checkout $BASE_COMMIT 2>&1 | tail -1
GROUP=DETBASE PREFILL_LEN=4096 LAYER_MAJOR=1 bash $SCR/ft_round_e1r001_launch.sh
run_seed7 "$ROUND_DIR/det_base.jsonl"

echo "=== [$(date '+%H:%M:%S')] compare full text ==="
$PY - "$ROUND_DIR/det_pr.jsonl" "$ROUND_DIR/det_base.jsonl" <<'EOF'
import json, sys
pr = json.loads(open(sys.argv[1]).readline())
ba = json.loads(open(sys.argv[2]).readline())
print("PR   ttft=%.3f decode=%.2f cached=%s" % (pr["ttft_s"], pr["decode_tps"], pr["cached_tokens"]))
print("BASE ttft=%.3f decode=%.2f cached=%s" % (ba["ttft_s"], ba["decode_tps"], ba["cached_tokens"]))
t1, t2 = pr["completion_text"], ba["completion_text"]
print("len PR=%d BASE=%d" % (len(t1), len(t2)))
if t1 == t2:
    print("DET_RESULT: BIT_EXACT_MATCH")
else:
    import difflib
    print("DET_RESULT: DIFFER")
    for i, (a, b) in enumerate(zip(t1, t2)):
        if a != b:
            print("first_diff at char %d: PR=%r BASE=%r" % (i, t1[max(0,i-40):i+40], t2[max(0,i-40):i+40]))
            break
EOF
echo "=== DET DONE ==="
trap - EXIT
restore_branch
