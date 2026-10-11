#!/bin/bash
set -eu

RID=E2-pre-gate-D01
CARD=T16
PORT=8095
WIN=49152
WT=/data2/FreeToken/wt/e2base
EXP_COMMIT=3db7b50
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
URL=http://127.0.0.1:$PORT/v1/chat/completions
HEALTH=http://127.0.0.1:$PORT/health
PY=/data2/FreeToken/venv/bin/python
SCR=/data2/FreeToken/scripts
D=/data2/_shared/runs/ft_rounds/$RID
LOCK=/data2/_shared/gpu.lock
SELF=$(basename "$0")
MODEL=/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay
BASE="--model-path $MODEL --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 0.0.0.0 --port $PORT --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned --moe-strategy offload --quant-backend moe.nvfp4=triton --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens $WIN --max-seq-len-override $WIN --enable-cache-report --tool-call-parser qwen3_coder --reasoning-parser qwen3"
FLAGS="--prefill-layer-major --max-prefill-length 4096 --enable-special-token-ckpt"
SPID=""

lock_take() {
  if (set -o noclobber; printf '{"owner":"%s","card":"%s","pid":%s}\n' "$RID" "$CARD" "$$" > "$LOCK") 2>/dev/null; then
    return 0
  fi
  echo "GATE-FAIL-LOCK $(cat "$LOCK" 2>/dev/null || true)"
  return 1
}

lock_release() {
  grep -q "\"owner\":\"$RID\"" "$LOCK" 2>/dev/null && rm -f "$LOCK" || true
}

stop() {
  if [ -n "$SPID" ]; then
    kill -- -"$SPID" 2>/dev/null || true
    sleep 25
    kill -9 -- -"$SPID" 2>/dev/null || true
    sleep 10
    SPID=""
  fi
  local gpu
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  echo "gpu-after=${gpu}MiB"
  [ "$gpu" -lt 1000 ] || { echo GATE-FAIL-VRAM-NOT-RELEASED; return 1; }
  lock_release
}

cleanup() { stop || true; }
trap cleanup EXIT

ok() {
  local r c dirty busy listener gpu kernels
  export PYTHONPATH=$WT/python
  r=$($PY -c 'import freetoken; print(freetoken.__file__)' 2>/dev/null)
  c=$(git -C "$WT" rev-parse --short=7 HEAD 2>/dev/null)
  dirty=$(git -C "$WT" status --porcelain --untracked-files=no 2>/dev/null | wc -l)
  busy=$(ps -eo args | awk -v self="$SELF" 'index($0,self)==0 && /ft serve|agent_trace\.py (replay|generate)|ft_probe|probe_ft_cold32k|cold_eq\.py|batch[0-9]+_/ && !/awk/' | wc -l)
  listener=$(ss -ltn | grep -c ":$PORT " || true)
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  kernels=0; $PY -c 'import freetoken.kernel._pinned_tensor, freetoken.kernel._cpu_moe' 2>/dev/null || kernels=1
  echo "GATE import=$r expect=$EXP commit=$c expect_commit=$EXP_COMMIT dirty=$dirty busy=$busy listener=$listener gpu_mib=$gpu kernels_missing=$kernels"
  [ "$r" = "$EXP" ] && [ "$c" = "$EXP_COMMIT" ] && [ "$dirty" = 0 ] && [ "$busy" = 0 ] && [ "$listener" = 0 ] && [ "$gpu" -lt 1000 ] && [ "$kernels" = 0 ] && lock_take
}

snap() {
  { date '+%F %T %Z'; echo "RID=$RID CARD=$CARD WT=$WT"; git -C "$WT" log -1 --format='%H %s'
    $PY -c 'import freetoken,torch; print(freetoken.__file__, torch.__version__, torch.version.cuda)'
    nvidia-smi --query-gpu=name,driver_version,memory.used,clocks.sm,temperature.gpu --format=csv
    numactl -H | grep -E 'size|free'; uptime; } > "$1/ENV.txt" 2>&1
}

start() {
  local out=$1 d0=$2
  mkdir -p "$out"; snap "$out"
  if [ "$d0" = d0 ]; then
    echo "env FT_DEV_D0=1 FT_DEV_D0_PATH=$out/d0 $LAUNCH ft serve $BASE $FLAGS" > "$out/SERVE_CMD.txt"
    env FT_DEV_D0=1 FT_DEV_D0_PATH="$out/d0" setsid $LAUNCH ft serve $BASE $FLAGS > "$out/serve.log" 2>&1 &
  else
    echo "env $LAUNCH ft serve $BASE $FLAGS" > "$out/SERVE_CMD.txt"
    setsid $LAUNCH ft serve $BASE $FLAGS > "$out/serve.log" 2>&1 &
  fi
  SPID=$!; echo "SPID=$SPID"
  local ready=0 health
  for i in $(seq 1 40); do
    sleep 15
    kill -0 "$SPID" 2>/dev/null || { echo SERVER_DIED; tail -20 "$out/serve.log"; break; }
    health=$(curl -s -m 10 "$HEALTH" || true)
    printf '%s\n' "$health" > "$out/health.json"
    if $PY -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("status") == "ok" else 1)' <<<"$health"; then
      curl -s -m 25 "$URL" -H 'Content-Type: application/json' -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"say ok"}],"max_tokens":2,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' > "$out/ready_sayok.json"
      grep -q '"content"' "$out/ready_sayok.json" && { ready=1; echo "READY $i"; break; }
    fi
  done
  grep -m1 -A1 'Parsed arguments' "$out/serve.log" > "$out/serve_args.txt" || true
  [ "$ready" = 1 ]
}

arm() {
  local arm=$1 wt=$2 commit=$3 d0=$4 out=$D/$arm
  WT=$wt; EXP_COMMIT=$commit; EXP=$WT/python/freetoken/__init__.py
  [ ! -e "$out" ] || { echo "GATE-FAIL-ARM-EXISTS $out"; return 1; }
  ok || { echo GATE-FAIL-ARM; return 1; }
  start "$out" "$d0" || { echo "$arm NOT-READY"; stop; return 1; }
  local p0
  p0=$(grep -c 'Prefill batch' "$out/serve.log" || true)
  $PY "$SCR/cold_eq.py" "$RID-$arm-det" "$out/det.json" 32052 128 2> "$out/det.err"
  $PY "$SCR/ft_probe_ckpt_tax.py" "$out/tax.json" "$arm" > "$out/tax.log" 2>&1
  sed 's/\x1b\[[0-9;]*m//g' "$out/serve.log" | grep -oE '#new-seq: [0-9]+, #new-token: [0-9]+, #cached-token: [0-9]+' | tail -n +$((p0+1)) > "$out/prefill_seq.txt"
  [ "$d0" != d0 ] || [ -s "$out/d0_prefill.jsonl" ]
  stop
}

compare_args() {
  local a=$1 b=$2 label=$3
  $PY "$SCR/serve_args_diff.py" "$a" "$b" >> "$D/args_diff.txt"
  $PY - "$a" "$b" "$SCR/serve_args_diff.py" <<'PY'
import re, runpy, sys
a, b, tool = sys.argv[1:4]
parse = runpy.run_path(tool)['parse']
left, right = parse(a), parse(b)
bad = []
for key in set(left) | set(right):
    lv, rv = left.get(key), right.get(key)
    if lv == rv:
        continue
    if key == 'unique_suffix' and lv is not None and rv is not None:
        if re.sub(r'\.pid=\d+', '.pid=<pid>', lv) == re.sub(r'\.pid=\d+', '.pid=<pid>', rv):
            continue
    if key == 'prefill_anchor_cut' and lv is None and rv == 'True':
        continue
    bad.append((key, lv, rv))
if bad:
    raise SystemExit('ARGS-DIFF-FAIL ' + repr(bad))
print('ARGS-OK')
PY
}

compare_h2d() {
  $PY - "$D/PARENT/d0_prefill.jsonl" "$D/NEW_resume/d0_prefill.jsonl" <<'PY' | tee "$D/gate_h2d.txt"
import json, sys
a = [json.loads(line) for line in open(sys.argv[1])]
b = [json.loads(line) for line in open(sys.argv[2])]
if len(a) != len(b):
    raise SystemExit('H2D LENGTH FAIL n_parent=%d n_new=%d' % (len(a), len(b)))
for i, (left, right) in enumerate(zip(a, b)):
    if (left['h2d_bytes'], left['d2d_bytes']) != (right['h2d_bytes'], right['d2d_bytes']):
        raise SystemExit('H2D DIFF index=%d parent=%r new=%r' % (i, left, right))
print('H2D SAME n_parent=%d n_new=%d' % (len(a), len(b)))
PY
}

echo "### $RID $CARD resume start $(date '+%F %T')"
[ -d "$D/PARENT" ] && [ -s "$D/PARENT/det.json" ] && [ -s "$D/PARENT/tax.json" ] && [ -s "$D/PARENT/d0_prefill.jsonl" ] || { echo GATE-FAIL-PARENT-INCOMPLETE; exit 7; }
for arm_name in NEW_resume PARENT_P NEW_P; do [ ! -e "$D/$arm_name" ] || { echo "GATE-FAIL-ARM-EXISTS $arm_name"; exit 7; }; done
arm NEW_resume /data2/FreeToken/wt/e1r008 f91054b d0
arm PARENT_P /data2/FreeToken/wt/e2base 3db7b50 nod0
arm NEW_P /data2/FreeToken/wt/e1r008 f91054b nod0
rm -f "$D/args_diff.txt"
compare_args "$D/PARENT/serve.log" "$D/NEW_resume/serve.log" D0
compare_args "$D/PARENT_P/serve.log" "$D/NEW_P/serve.log" PROD
$PY - "$D/PARENT/det.json" "$D/NEW_resume/det.json" "$D/PARENT_P/det.json" "$D/NEW_P/det.json" <<'PY' | tee "$D/gate_text.txt"
import json, sys
for label, left, right in zip(('TEXT', 'TEXT_PROD'), sys.argv[1::2], sys.argv[2::2]):
    a, b = json.load(open(left))['text'], json.load(open(right))['text']
    if a != b:
        raise SystemExit('%s DIFF %d %d' % (label, len(a), len(b)))
    print('%s BIT_EXACT_MATCH %d' % (label, len(a)))
PY
cmp -s "$D/PARENT/prefill_seq.txt" "$D/NEW_resume/prefill_seq.txt" && echo 'SEQ SAME' | tee "$D/gate_seq.txt" || { echo 'SEQ DIFF' | tee "$D/gate_seq.txt"; exit 7; }
cmp -s "$D/PARENT_P/prefill_seq.txt" "$D/NEW_P/prefill_seq.txt" && echo 'SEQ_PROD SAME' | tee -a "$D/gate_seq.txt" || { echo 'SEQ_PROD DIFF' | tee -a "$D/gate_seq.txt"; exit 7; }
compare_h2d
echo "### $RID $CARD resume done $(date '+%F %T')"
