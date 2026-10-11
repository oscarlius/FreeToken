#!/usr/bin/env bash
set -euo pipefail

: "${FT_T17_SOURCE_ROOT:?sealed v3 source archive required}"
: "${FT_T17_BATCH:?allocated batch required}"
: "${FT_T17_INPUTS:?sealed realinput28 required}"
: "${FT_T17_CLOSURE_BINDING:?sealed candidate T16 closure binding required}"
: "${FT_T17_SOURCE_REVIEW:?independent startup review required}"
: "${FT_T17_SOURCE_REVIEW_SHA256:?caller-pinned startup review SHA required}"
: "${FT_T17_PREFLIGHT_ARTIFACT:?external preflight artifact path required}"
: "${FT_T17_ROUNDS:?canonical rounds root required}"
: "${FT_T17_CANDIDATE_WORKTREE:?exact candidate worktree required}"

if (( $# != 2 )) || [[ "$2" != "--run" ]]; then
  echo "usage: batchNN_T17_v3.sh E2-R035..E2-R039 --run" >&2
  exit 64
fi
rid="$1"
case "$rid" in E2-R035|E2-R036|E2-R037|E2-R038|E2-R039) ;; *) exit 64 ;; esac
cases="${FT_T17_CASES:-all}"
resume_args=()
case "$cases" in
  all)
    [[ -z "${FT_T17_RESUME_REVIEW:-}${FT_T17_RESUME_REVIEW_SHA256:-}" ]] || exit 64
    ;;
  remaining)
    : "${FT_T17_RESUME_REVIEW:?independent retained-case review required}"
    : "${FT_T17_RESUME_REVIEW_SHA256:?pinned retained-case review SHA required}"
    resume_args=(--resume-review "$FT_T17_RESUME_REVIEW" --resume-review-sha256 "$FT_T17_RESUME_REVIEW_SHA256")
    ;;
  *) exit 64 ;;
esac
exec /data2/FreeToken/venv/bin/python -u "$FT_T17_SOURCE_ROOT/t17_continuation_runner_v2.py" \
  --realinput28 "$FT_T17_INPUTS" --candidate-worktree "$FT_T17_CANDIDATE_WORKTREE" \
  --candidate-sha a9dca443cd07e1f60d1533e0a678935a09d21636 \
  --parent-sha e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7 \
  --run-kind t17 --cases "$cases" "${resume_args[@]}" --envelope-cases sample4 --rid "$rid" --batch "$FT_T17_BATCH" --run \
  --cpu-report "${FT_T17_STAGE}/startup_cpu_report.json" --source-root "$FT_T17_SOURCE_ROOT" \
  --source-review "$FT_T17_SOURCE_REVIEW" --source-review-sha256 "$FT_T17_SOURCE_REVIEW_SHA256" \
  --rounds "$FT_T17_ROUNDS" --closure-binding "$FT_T17_CLOSURE_BINDING" \
  --prior-t16-rid E2-R037-gate-D14 --prior-t16-batch 66 --directory "$FT_T17_ROUNDS/$rid" \
  --preflight-artifact "$FT_T17_PREFLIGHT_ARTIFACT"
