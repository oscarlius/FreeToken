#!/bin/bash
# 通用单组测试：cold_long(warmup)x2 + short x2，结果写入指定轮次目录
# 用法：ft_run_group2.sh <ROUND_DIR> <GROUP>
set -e
ROUND_DIR="$1"
GROUP="$2"
OUT="$ROUND_DIR/group${GROUP}.jsonl"
PY=/data2/FreeToken/venv/bin/python
SC=/data2/FreeToken/scripts/ft_perf_decomp.py
rm -f "$OUT"
echo "=== group $GROUP -> $OUT ==="
$PY $SC run --fixture cold_long --warmup --repeat 2 --target 32000 --out "$OUT"
$PY $SC run --fixture short --repeat 2 --out "$OUT"
echo "=== summary ==="
$PY -c "import json;rs=[json.loads(l) for l in open('$OUT')];[print(r['label'],'ttft=',r.get('ttft_s'),'decode=',r.get('decode_tps'),'cached=',r.get('cached_tokens'),'ok=',r.get('expect_ok')) for r in rs]"
