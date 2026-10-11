#!/usr/bin/env bash
# Versioned T20 launcher: arguments must provide dynamic parent/candidate/T16 proof.
set -euo pipefail
: "${FT_T20_RUNNER:=development/t17_continuation_runner_v2.py}"
exec python "$FT_T20_RUNNER" --run-kind t20 "$@"