#!/usr/bin/env bash
# D17 R041 preflight only.  It cannot start a GPU service or replace warm restore
# with a cold probe; a separately frozen shared T16/continuation executor owns that.
set -euo pipefail

: "${FT_D17_REALINPUT28:?sealed realinput28 source required}"
: "${FT_D17_ACCEPTED_T17:?sealed accepted T17 closure required}"
: "${FT_D17_INDEPENDENT_REVIEW:?sealed independent T17 review required}"
: "${FT_D17_GPU_LOCK:=/data2/_shared/gpu.lock}"

if (( $# != 1 )); then
  echo "usage: batchNN_E2-R041_v2.sh E2-R041-gate-D17" >&2
  exit 64
fi

exec /data2/FreeToken/venv/bin/python -u /data2/FreeToken/development/d17_gate_case.py \
  --rid "$1" --realinput28 "$FT_D17_REALINPUT28" \
  --accepted-t17 "$FT_D17_ACCEPTED_T17" --independent-review "$FT_D17_INDEPENDENT_REVIEW" \
  --gpu-lock "$FT_D17_GPU_LOCK"
