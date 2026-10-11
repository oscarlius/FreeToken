#!/bin/bash
# batch20_E2-pre-gate-D01.sh —— 由 plan/01_测试与调研/README.md §4 模板生成
set -u
# ================= 参数区（按卡片填写）=================
RID=E2-pre-gate-D01
CARD=T16
WT=/data2/FreeToken/wt/e2base
EXP_COMMIT=3db7b50
PORT=8095
WIN=49152
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
# ================= 固定区（不得修改）=================
URL=http://127.0.0.1:$PORT/v1/chat/completions
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64:${LD_LIBRARY_PATH:-}
export VIRTUAL_ENV=/data2/FreeToken/venv PYTHONUNBUFFERED=1
PY=/data2/FreeToken/venv/bin/python
SCR=/data2/FreeToken/scripts
D=/data2/_shared/runs/ft_rounds/$RID
LOCK=/data2/_shared/gpu.lock
SELF=$(basename "$0")
[ -e "$D" ] && { echo "GATE-FAIL-RID-EXISTS $D"; exit 9; }
mkdir -p "$D" && cp "$0" "$D/batch.sh"
export PYTHONPATH=$WT/python
EXP=$WT/python/freetoken/__init__.py
MODEL=/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay
BASE="--model-path $MODEL --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 0.0.0.0 --port $PORT --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned --moe-strategy offload --quant-backend moe.nvfp4=triton --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens $WIN --max-seq-len-override $WIN --enable-cache-report --tool-call-parser qwen3_coder --reasoning-parser qwen3"
SPID=""
lock_take() { if [ -e $LOCK ] && ! grep -q "\"owner\":\"$RID\"" $LOCK; then echo "GATE-FAIL-LOCK $(cat $LOCK)"; return 1; fi
  echo "{\"owner\":\"$RID\",\"card\":\"$CARD\",\"since\":\"$(date '+%F %T')\",\"pid\":$$}" > $LOCK; }
lock_release() { grep -q "\"owner\":\"$RID\"" $LOCK 2>/dev/null && rm -f $LOCK; }
cleanup() { [ -n "$SPID" ] && kill -- -$SPID 2>/dev/null; lock_release; }
trap cleanup EXIT
ok() {
  local R=$($PY -c "import freetoken;print(freetoken.__file__)" 2>/dev/null)
  local C=$(git -C $WT rev-parse --short=7 HEAD 2>/dev/null)
  local DIRTY=$(git -C $WT status --porcelain --untracked-files=no 2>/dev/null | wc -l)
  local B=$(ps -eo args | awk -v self="$SELF" 'index($0,self)==0 && /ft serve|agent_trace\.py (replay|generate)|ft_probe|probe_ft_cold32k|cold_eq\.py|batch[0-9]+_/ && !/awk/' | wc -l)
  local L=$(ss -ltn | grep -c ":$PORT ")
  local G=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  local K=0; $PY -c "import freetoken.kernel._pinned_tensor, freetoken.kernel._cpu_moe" 2>/dev/null || K=1
  echo "GATE import=$R expect=$EXP commit=$C expect_commit=$EXP_COMMIT dirty=$DIRTY busy=$B listener=$L gpu_mib=$G kernels_missing=$K"
  [ "$R" = "$EXP" ] || { echo GATE-FAIL-IMPORT; return 1; }
  [ "$C" = "$EXP_COMMIT" ] || { echo GATE-FAIL-COMMIT; return 1; }
  [ "$DIRTY" = 0 ] || { echo GATE-FAIL-DIRTY-TREE; return 1; }
  [ "$K" = 0 ] || { echo GATE-FAIL-KERNELS; return 1; }
  [ "$L" = 0 ] || { echo GATE-FAIL-LISTENER; return 1; }
  [ "$G" -lt 1000 ] || { echo GATE-FAIL-VRAM; return 1; }
  [ "$B" = 0 ] || { echo GATE-FAIL-SINGLE-WRITER; ps -eo pid,args | awk -v self="$SELF" 'index($0,self)==0 && /ft serve|agent_trace|ft_probe|probe_ft|cold_eq|batch[0-9]+_/ && !/awk/'; return 1; }
  lock_take || return 1
}
snap() { { date '+%F %T %Z'; echo "RID=$RID CARD=$CARD WT=$WT"; git -C $WT log -1 --format='%H %s';
  $PY -c "import freetoken,torch;print(freetoken.__file__, torch.__version__, torch.version.cuda)";
  nvidia-smi --query-gpu=name,driver_version,memory.used,clocks.sm,temperature.gpu --format=csv;
  numactl -H | grep -E 'size|free'; uptime; ps -eo pid,psr,pcpu,args --sort=-pcpu | head -8 | cut -c1-160; } > "$1/ENV.txt" 2>&1; }
# 用法：start <臂目录> "<额外环境变量，空格分隔，可为空>" <额外 ft serve 参数...>
start() { local OUT=$1 AENV=$2; shift 2; mkdir -p $OUT; snap $OUT; local T0=$(date +%s)
  echo "env $AENV $LAUNCH ft serve $BASE $*" > $OUT/SERVE_CMD.txt
  env $AENV setsid $LAUNCH ft serve $BASE "$@" > $OUT/serve.log 2>&1 &
  SPID=$!; READY=0; echo "SPID=$SPID"
  for i in $(seq 1 40); do sleep 15
    if kill -0 $SPID 2>/dev/null; then
      if curl -s -m 25 $URL -H 'Content-Type: application/json' -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"say ok"}],"max_tokens":2,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' | grep -q '"content"'; then READY=1; echo "READY $(( $(date +%s)-T0 ))s"; break; fi
    else echo SERVER_DIED; tail -20 $OUT/serve.log; break; fi
  done
  grep -m1 -A1 'Parsed arguments' $OUT/serve.log > $OUT/serve_args.txt
  echo "taskset: $(taskset -cp $SPID 2>/dev/null)"; }
stop() { kill -- -$SPID 2>/dev/null || kill $SPID 2>/dev/null; sleep 25; kill -9 -- -$SPID 2>/dev/null; sleep 10; SPID=""
  local G=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); echo "gpu-after=${G}MiB"
  [ "$G" -lt 1000 ] || { echo "GATE-FAIL-VRAM-NOT-RELEASED"; exit 8; }
  lock_release; }
# ================= 主体区（逐字取自卡片）=================
echo "### $RID $CARD start $(date '+%F %T')"
FLAGS="--prefill-layer-major --max-prefill-length 4096 --enable-special-token-ckpt"
arm() { local ARM=$1; WT=$2; EXP_COMMIT=$3; local D0ENV=$4; export PYTHONPATH=$WT/python; EXP=$WT/python/freetoken/__init__.py; local O=$D/$ARM
  ok || exit 7
  if [ "$D0ENV" = d0 ]; then start $O "FT_DEV_D0=1 FT_DEV_D0_PATH=$O/d0" $FLAGS; else start $O "" $FLAGS; fi
  [ $READY = 1 ] || { echo "$ARM NOT-READY"; stop; exit 6; }
  local P0=$(grep -c "Prefill batch" $O/serve.log)   # 就绪探测 "say ok" 产生的行不参与比较
  $PY $SCR/cold_eq.py "$RID-det" $O/det.json 32052 128 2> $O/det.err; echo "$ARM det rc=$?"
  $PY $SCR/ft_probe_ckpt_tax.py $O/tax.json $ARM > $O/tax.log 2>&1; echo "$ARM tax rc=$?"
  sed "s/\x1b\[[0-9;]*m//g" $O/serve.log | grep -oE "#new-seq: [0-9]+, #new-token: [0-9]+, #cached-token: [0-9]+" | tail -n +$((P0+1)) > $O/prefill_seq.txt
  stop
}
arm PARENT    /data2/FreeToken/wt/e2base 3db7b50 d0
arm NEW       /data2/FreeToken/wt/e1r008 f91054b d0
arm PARENT_P  /data2/FreeToken/wt/e2base 3db7b50 nod0
arm NEW_P     /data2/FreeToken/wt/e1r008 f91054b nod0
$PY $SCR/serve_args_diff.py $D/PARENT/serve.log $D/NEW/serve.log > $D/args_diff.txt 2>&1; $PY $SCR/serve_args_diff.py $D/PARENT_P/serve.log $D/NEW_P/serve.log >> $D/args_diff.txt 2>&1; cat $D/args_diff.txt
$PY -c "import json,sys;a=json.load(open(sys.argv[1]))['text'];b=json.load(open(sys.argv[2]))['text'];print('TEXT', 'BIT_EXACT_MATCH' if a==b else 'DIFF', len(a), len(b))" $D/PARENT/det.json $D/NEW/det.json | tee $D/gate_text.txt
$PY -c "import json,sys;a=json.load(open(sys.argv[1]))['text'];b=json.load(open(sys.argv[2]))['text'];print('TEXT_PROD', 'BIT_EXACT_MATCH' if a==b else 'DIFF', len(a), len(b))" $D/PARENT_P/det.json $D/NEW_P/det.json | tee -a $D/gate_text.txt
( cmp -s $D/PARENT/prefill_seq.txt $D/NEW/prefill_seq.txt && echo "SEQ SAME" || echo "SEQ DIFF" ) | tee $D/gate_seq.txt
( cmp -s $D/PARENT_P/prefill_seq.txt $D/NEW_P/prefill_seq.txt && echo "SEQ_PROD SAME" || echo "SEQ_PROD DIFF" ) | tee -a $D/gate_seq.txt
$PY -c "
import json,sys
A=[json.loads(l) for l in open(sys.argv[1])]; B=[json.loads(l) for l in open(sys.argv[2])]
same = all(a['h2d_bytes']==b['h2d_bytes'] and a['d2d_bytes']==b['d2d_bytes'] for a,b in zip(A,B))
print('H2D', 'SAME' if same else 'DIFF', 'n_parent=%d n_new=%d' % (len(A), len(B)))" $D/PARENT/d0_prefill.jsonl $D/NEW/d0_prefill.jsonl | tee $D/gate_h2d.txt
echo "### $RID $CARD done $(date '+%F %T')"
