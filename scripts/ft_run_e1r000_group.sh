#!/bin/bash
# E1-R000 单组测试：cold_long x2 + short x2，结果写入轮次工件目录
# 用法：ft_run_e1r000_group.sh <group>   (group = A|B|C)
set -e
GROUP="$1"
ROUND="${ROUND:-E1-R000}"
TARGET="${TARGET:-32000}"
ROUND_DIR=/data2/_shared/runs/ft_rounds/_e1/$ROUND
OUT="$ROUND_DIR/group${GROUP}.jsonl"
PY=/data2/FreeToken/venv/bin/python
SC=/data2/FreeToken/scripts/ft_perf_decomp.py
rm -f "$OUT"
echo "=== group $GROUP -> $OUT ==="
$PY $SC run --fixture cold_long --repeat 2 --warmup --target $TARGET --out "$OUT"
$PY $SC run --fixture short --repeat 2 --out "$OUT"
echo "=== summary ==="
$PY -c "import json;rs=[json.loads(l) for l in open('$OUT')];[print(r['label'],'ttft=',r.get('ttft_s'),'decode=',r.get('decode_tps'),'cached=',r.get('cached_tokens'),'ok=',r.get('expect_ok')) for r in rs]"
