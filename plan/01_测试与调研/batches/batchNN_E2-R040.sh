#!/usr/bin/env bash
# Complete T20: continuation followed by production and native D16 measurements
# in the same owned lifecycle. Only the reviewed source package is executable.
set -euo pipefail
(( $# == 2 )) || { echo 'usage: batchNN_E2-R040.sh ASSIGNED_BATCH check|run' >&2; exit 64; }
[[ "$1" =~ ^[1-9][0-9]*$ ]] || exit 64
[[ "$2" == check || "$2" == run ]] || exit 64
: "${FT_T20_SOURCE_ROOT:?reviewed frozen executor source directory required}"
export FT_T20_FULL=1
exec bash "$FT_T20_SOURCE_ROOT/batchNN_E2-R040_continuation_v3.sh" "$@"
