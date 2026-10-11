#!/bin/bash
set -euo pipefail

RID=E2-pre-gate-D01
CARD=T16
PORT=8095
WIN=49152
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
PY=/data2/FreeToken/venv/bin/python
SCR=/data2/FreeToken/scripts
D=/data2/_shared/runs/ft_rounds/$RID
LOCK=/data2/_shared/gpu.lock
MODEL=/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay
COLD_ID=E2-pre-gate-D01-det
BASE="--model-path $MODEL --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 0.0.0.0 --port $PORT --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned --moe-strategy offload --quant-backend moe.nvfp4=triton --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens $WIN --max-seq-len-override $WIN --enable-cache-report --tool-call-parser qwen3_coder --reasoning-parser qwen3"
FLAGS="--prefill-layer-major --max-prefill-length 4096 --enable-special-token-ckpt"
SPID=""
SELF=$(basename "$0")

release_lock() { grep -q "\"owner\":\"$RID\"" "$LOCK" 2>/dev/null && rm -f "$LOCK" || true; }
stop() {
  if [ -n "$SPID" ]; then kill -- -"$SPID" 2>/dev/null || true; sleep 25; kill -9 -- -"$SPID" 2>/dev/null || true; sleep 10; SPID=""; fi
  local gpu; gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  echo "gpu-after=${gpu}MiB"; [ "$gpu" -lt 1000 ]; release_lock
}
cleanup() { stop || true; }
trap cleanup EXIT
take_lock() {
  (set -o noclobber; printf '{"owner":"%s","card":"%s","pid":%s}\n' "$RID" "$CARD" "$$" > "$LOCK") 2>/dev/null && return 0
  echo "GATE-FAIL-LOCK $(cat "$LOCK" 2>/dev/null || true)"; return 1
}
gate() {
  export PYTHONPATH=$WT/python
  local import_path commit dirty busy listener gpu kernels
  import_path=$($PY -c 'import freetoken;print(freetoken.__file__)' 2>/dev/null)
  commit=$(git -C "$WT" rev-parse --short=7 HEAD 2>/dev/null)
  dirty=$(git -C "$WT" status --porcelain --untracked-files=no | wc -l)
  busy=$(ps -eo args | awk -v self="$SELF" 'index($0,self)==0 && /ft serve|agent_trace\.py (replay|generate)|ft_probe|probe_ft_cold32k|cold_eq\.py|batch[0-9]+_/ && !/awk/' | wc -l)
  listener=$(ss -ltn | grep -c ":$PORT " || true)
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  kernels=0; $PY -c 'import freetoken.kernel._pinned_tensor,freetoken.kernel._cpu_moe' 2>/dev/null || kernels=1
  echo "GATE import=$import_path expect=$EXP commit=$commit expect_commit=$EXP_COMMIT dirty=$dirty busy=$busy listener=$listener gpu_mib=$gpu kernels_missing=$kernels"
  [ "$import_path" = "$EXP" ] && [ "$commit" = "$EXP_COMMIT" ] && [ "$dirty" = 0 ] && [ "$busy" = 0 ] && [ "$listener" = 0 ] && [ "$gpu" -lt 1000 ] && [ "$kernels" = 0 ] && take_lock
}
snap() {
  { date '+%F %T %Z'; echo "RID=$RID CARD=$CARD WT=$WT"; git -C "$WT" log -1 --format='%H %s'; $PY -c 'import freetoken,torch;print(freetoken.__file__,torch.__version__,torch.version.cuda)'; nvidia-smi --query-gpu=name,driver_version,memory.used,clocks.sm,temperature.gpu --format=csv; numactl -H | grep -E 'size|free'; } > "$1/ENV.txt" 2>&1
}
start() {
  local out=$1 d0=$2 health ready i
  mkdir -p "$out"; snap "$out"
  if [ "$d0" = d0 ]; then
    echo "env FT_DEV_D0=1 FT_DEV_D0_PATH=$out/d0 $LAUNCH ft serve $BASE $FLAGS" > "$out/SERVE_CMD.txt"
    env FT_DEV_D0=1 FT_DEV_D0_PATH="$out/d0" setsid $LAUNCH ft serve $BASE $FLAGS > "$out/serve.log" 2>&1 &
  else
    echo "env $LAUNCH ft serve $BASE $FLAGS" > "$out/SERVE_CMD.txt"
    setsid $LAUNCH ft serve $BASE $FLAGS > "$out/serve.log" 2>&1 &
  fi
  SPID=$!; echo "SPID=$SPID"; ready=0
  for i in $(seq 1 40); do
    sleep 15; kill -0 "$SPID" 2>/dev/null || { echo SERVER_DIED; tail -20 "$out/serve.log"; break; }
    health=$(curl -s -m 10 "http://127.0.0.1:$PORT/health" || true); printf '%s\n' "$health" > "$out/health.json"
    if $PY -c 'import json,sys;raise SystemExit(0 if json.load(sys.stdin).get("status")=="ok" else 1)' <<<"$health"; then
      curl -s -m 25 "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"say ok"}],"max_tokens":2,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' > "$out/ready_sayok.json"
      grep -q '"content"' "$out/ready_sayok.json" && { ready=1; echo "READY $i"; break; }
    fi
  done
  grep -m1 -A1 'Parsed arguments' "$out/serve.log" > "$out/serve_args.txt" || true
  [ "$ready" = 1 ]
}
run_arm() {
  local arm_name=$1 arm_wt=$2 arm_commit=$3 arm_d0=$4 compare_to=${5:-} out p0
  out=$D/$arm_name; WT=$arm_wt; EXP_COMMIT=$arm_commit; EXP=$WT/python/freetoken/__init__.py
  [ ! -e "$out" ] || { echo "GATE-FAIL-ARM-EXISTS $out"; return 1; }
  gate || { echo GATE-FAIL-ARM; return 1; }
  start "$out" "$arm_d0" || { echo "$arm_name NOT-READY"; stop; return 1; }
  if [ -n "$compare_to" ]; then
    $PY "$SCR/serve_args_diff.py" "$compare_to/serve.log" "$out/serve.log" > "$out/args_diff.txt"
    strict_args "$compare_to/serve.log" "$out/serve.log" >> "$out/args_diff.txt"
  fi
  p0=$(grep -c 'Prefill batch' "$out/serve.log" || true)
  $PY "$SCR/cold_eq.py" "$COLD_ID" "$out/det.json" 32052 128 2> "$out/det.err"
  $PY "$SCR/ft_probe_ckpt_tax.py" "$out/tax.json" "$arm_name" > "$out/tax.log" 2>&1
  sed 's/\x1b\[[0-9;]*m//g' "$out/serve.log" | grep -oE '#new-seq: [0-9]+, #new-token: [0-9]+, #cached-token: [0-9]+' | tail -n +$((p0+1)) > "$out/prefill_seq.txt"
  [ -s "$out/det.json" ] && [ -s "$out/tax.json" ] && [ -s "$out/prefill_seq.txt" ]
  if [ "$arm_d0" = d0 ]; then [ -s "$out/d0_prefill.jsonl" ]; else ! find "$out" -maxdepth 1 -name 'd0_*' -type f | grep -q .; fi
  stop
}
strict_args() {
  $PY - "$1" "$2" "$SCR/serve_args_diff.py" <<'PY'
import ast,re,runpy,sys
a,b,tool=sys.argv[1:]; parse=runpy.run_path(tool)['parse']; left,right=parse(a),parse(b); bad=[]
for side, values in (('parent', left), ('new', right)):
    missing = {'model_path', 'server_port', 'special_token_ckpt'} - set(values)
    if missing: bad.append((side, 'missing_required', sorted(missing)))
for key in set(left)|set(right):
    lv,rv=left.get(key),right.get(key)
    if lv==rv: continue
    if key=='_unique_suffix' and lv and rv:
        try: lp,rp=ast.literal_eval(lv),ast.literal_eval(rv)
        except (SyntaxError,ValueError): lp=rp=None
        if isinstance(lp,str) and isinstance(rp,str) and re.fullmatch(r'\.pid=\d+',lp) and re.fullmatch(r'\.pid=\d+',rp): continue
    if key=='prefill_anchor_cut' and lv is None and rv=='True': continue
    bad.append((key,lv,rv))
if bad: raise SystemExit('ARGS-DIFF-FAIL '+repr(bad))
print('ARGS-OK')
PY
}
strict_text() {
  $PY - "$1" "$2" "$3" <<'PY'
import json,sys
a,b,label=sys.argv[1:]; left,right=json.load(open(a))['text'],json.load(open(b))['text']
if not left or not right or left!=right: raise SystemExit('%s DIFF_OR_EMPTY %d %d'%(label,len(left),len(right)))
print('%s BIT_EXACT_MATCH %d'%(label,len(left)))
PY
}
strict_det_inputs() {
  $PY - "$@" <<'PY'
import json,sys
records=[json.load(open(path))['record'] for path in sys.argv[1:]]
keys=('cold_id','built_tokens','prompt_tokens','cached_tokens')
values=[tuple(record.get(key) for key in keys) for record in records]
if any(not record['cold_id'] or record['cached_tokens'] != 0 for record in records):
    raise SystemExit('DET INPUT MISSING_OR_CACHED '+repr(values))
if len(set(values)) != 1:
    raise SystemExit('DET INPUT DIFF '+repr(values))
print('DET INPUT SAME '+repr(values[0]))
PY
}
strict_h2d() {
  $PY - "$1" "$2" <<'PY'
import json,sys
a=[json.loads(x) for x in open(sys.argv[1])]; b=[json.loads(x) for x in open(sys.argv[2])]
if not a or not b or len(a)!=len(b): raise SystemExit('H2D EMPTY_OR_LENGTH %d %d'%(len(a),len(b)))
for i,(x,y) in enumerate(zip(a,b)):
    if (x['h2d_bytes'],x['d2d_bytes']) != (y['h2d_bytes'],y['d2d_bytes']): raise SystemExit('H2D DIFF %d'%i)
print('H2D SAME n_parent=%d n_new=%d'%(len(a),len(b)))
PY
}
strict_nonempty_cmp() { [ -s "$1" ] && [ -s "$2" ] && cmp -s "$1" "$2"; }
self_test() {
  local q; q=$(mktemp -d); printf '{"h2d_bytes":1,"d2d_bytes":2}\n' > "$q/a"; printf '{"h2d_bytes":2,"d2d_bytes":2}\n' > "$q/b"
  if strict_h2d "$q/a" "$q/b"; then echo SELFTEST-FAIL; rm -rf "$q"; return 1; fi
  rm -rf "$q"; echo SELFTEST-STRICT-OK
}

echo "### $RID $CARD batch22 start $(date '+%F %T')"
[ -d "$D/PARENT" ] && [ -s "$D/PARENT/SERVE_CMD.txt" ] && [ -s "$D/PARENT/serve.log" ] && [ -s "$D/PARENT/det.json" ] && [ -s "$D/PARENT/tax.json" ] && [ -s "$D/PARENT/prefill_seq.txt" ] && [ -s "$D/PARENT/d0_prefill.jsonl" ] || { echo GATE-FAIL-PARENT-INCOMPLETE; exit 7; }
for name in NEW_resume PARENT_P NEW_P; do [ ! -e "$D/$name" ] || { echo "GATE-FAIL-ARM-EXISTS $name"; exit 7; }; done
self_test
run_arm NEW_resume /data2/FreeToken/wt/e1r008 f91054b d0 "$D/PARENT"
rm -f "$D/args_diff_batch22.txt"
$PY "$SCR/serve_args_diff.py" "$D/PARENT/serve.log" "$D/NEW_resume/serve.log" > "$D/args_diff_batch22.txt"
strict_args "$D/PARENT/serve.log" "$D/NEW_resume/serve.log" >> "$D/args_diff_batch22.txt"
run_arm PARENT_P /data2/FreeToken/wt/e2base 3db7b50 nod0
run_arm NEW_P /data2/FreeToken/wt/e1r008 f91054b nod0 "$D/PARENT_P"
$PY "$SCR/serve_args_diff.py" "$D/PARENT_P/serve.log" "$D/NEW_P/serve.log" >> "$D/args_diff_batch22.txt"
strict_args "$D/PARENT_P/serve.log" "$D/NEW_P/serve.log" >> "$D/args_diff_batch22.txt"
strict_text "$D/PARENT/det.json" "$D/NEW_resume/det.json" TEXT | tee "$D/gate_text_batch22.txt"
strict_text "$D/PARENT_P/det.json" "$D/NEW_P/det.json" TEXT_PROD | tee -a "$D/gate_text_batch22.txt"
strict_det_inputs "$D/PARENT/det.json" "$D/NEW_resume/det.json" "$D/PARENT_P/det.json" "$D/NEW_P/det.json" | tee "$D/gate_det_inputs_batch22.txt"
strict_nonempty_cmp "$D/PARENT/prefill_seq.txt" "$D/NEW_resume/prefill_seq.txt" && echo 'SEQ SAME' | tee "$D/gate_seq_batch22.txt" || { echo 'SEQ DIFF_OR_EMPTY' | tee "$D/gate_seq_batch22.txt"; exit 7; }
strict_nonempty_cmp "$D/PARENT_P/prefill_seq.txt" "$D/NEW_P/prefill_seq.txt" && echo 'SEQ_PROD SAME' | tee -a "$D/gate_seq_batch22.txt" || { echo 'SEQ_PROD DIFF_OR_EMPTY' | tee -a "$D/gate_seq_batch22.txt"; exit 7; }
strict_h2d "$D/PARENT/d0_prefill.jsonl" "$D/NEW_resume/d0_prefill.jsonl" | tee "$D/gate_h2d_batch22.txt"
echo "### $RID $CARD batch22 done $(date '+%F %T')"
