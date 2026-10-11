#!/usr/bin/env bash
set -euo pipefail

: "${FT_T17_STAGE:?frozen continuation stage required}"
: "${FT_T17_BATCH:?assigned batch required}"
: "${FT_T17_BATCH_TEMPLATE:?frozen reviewed batch template required}"
: "${FT_T17_INPUTS:?frozen target-tokenizer input matrix required}"
: "${FT_T17_CLOSURE_BINDING:?frozen R032 closure binding required}"

if (( $# != 1 )) && { (( $# != 2 )) || [[ "$2" != "--run" ]]; }; then
  echo "usage: batchNN_T17.sh RID [--run]" >&2
  exit 64
fi
rid="${1:?RID is the first positional argument}"
rounds="${FT_T17_ROUNDS:-/data2/_shared/runs/ft_rounds}"
exec /data2/FreeToken/venv/bin/python -u "$FT_T17_STAGE/t17_continuation_runner.py" \
  --rid "$rid" --batch "$FT_T17_BATCH" --inputs "$FT_T17_INPUTS" \
  --closure-binding "$FT_T17_CLOSURE_BINDING" --directory "$rounds/$rid" --run
