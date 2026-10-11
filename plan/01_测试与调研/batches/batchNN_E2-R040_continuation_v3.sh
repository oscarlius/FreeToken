#!/usr/bin/env bash
# T20 continuation component only; other T20 measurements run separately.
# The existing selector recomputes R041 proof: valid => four, otherwise all 28.
set -euo pipefail
if (( $# != 2 )); then
  echo 'usage: batchNN_E2-R040_continuation_v3.sh ASSIGNED_BATCH check|run' >&2
  exit 64
fi
[[ "$1" =~ ^[1-9][0-9]*$ ]] || exit 64
[[ "$2" == check || "$2" == run ]] || exit 64
: "${FT_T20_SOURCE_ROOT:?reviewed frozen executor source directory required}"
: "${FT_T20_REALINPUT28:?sealed real inputs required}"
: "${FT_T20_CANDIDATE_SHA:?full integration commit required}"
: "${FT_T20_PARENT_SHA:?full parent commit required}"
argv=(/data2/FreeToken/venv/bin/python -u "$FT_T20_SOURCE_ROOT/t17_continuation_runner_v2.py"
  --run-kind t20 --rid E2-R040 --batch "$1"
  --realinput28 "$FT_T20_REALINPUT28"
  --candidate-worktree /data2/FreeToken/wt/e2base1-ordinary-rewind
  --candidate-sha "$FT_T20_CANDIDATE_SHA" --parent-sha "$FT_T20_PARENT_SHA"
  --cases t20-sample4 --envelope-cases sample4)
if [[ "${FT_T20_FULL:-0}" == 1 ]]; then
  : "${FT_T20_D16_SOURCE_REVIEW:?actual D16 startup review required for full T20}"
  : "${FT_T20_D16_SOURCE_REVIEW_SHA256:?D16 startup review SHA required for full T20}"
  argv+=(--t20-full --d16-source-review "$FT_T20_D16_SOURCE_REVIEW"
    --d16-source-review-sha256 "$FT_T20_D16_SOURCE_REVIEW_SHA256")
elif [[ "${FT_T20_FULL:-0}" != 0 ]]; then
  echo 'FT_T20_FULL must be 0 or 1' >&2
  exit 64
fi
# All fields are forwarded without inventing absent R041 acceptance evidence.
for key in r041_round r041_independent_review caller_ir_sha256 accepted_t17_path \
  accepted_t17_review expected_tag expected_d17_commit expected_d17_worktree \
  expected_gate_case_sha256 expected_artifacts_sha256 expected_t16_runner_sha256 \
  expected_parser_sha256 expected_d04_checker_sha256 expected_verifier_sha256; do
  variable="FT_T20_${key^^}"
  if [[ -n "${!variable:-}" ]]; then argv+=("--${key//_/-}" "${!variable}"); fi
done
if [[ "$2" == run ]]; then
  for key in cpu_report closure_binding prior_t16_rid prior_t16_batch \
    source_review source_review_sha256 preflight_artifact; do
    variable="FT_T20_${key^^}"
    [[ -n "${!variable:-}" ]] || { echo "$variable required for run" >&2; exit 64; }
    argv+=("--${key//_/-}" "${!variable}")
  done
  argv+=(--source-root "$FT_T20_SOURCE_ROOT"
    --rounds /data2/_shared/runs/ft_rounds
    --directory /data2/_shared/runs/ft_rounds/E2-R040 --run)
fi
export PYTHONPATH="$FT_T20_SOURCE_ROOT:/data2/FreeToken/wt/e2base1-ordinary-rewind/scripts:/data2/FreeToken/wt/e2base1-ordinary-rewind/python"
if [[ "$2" == check ]]; then
  : "${FT_CPU_GUARD_ROOT:?CPU check requires the existing socket guard source directory}"
  export PYTHONPATH="$FT_T20_SOURCE_ROOT:$FT_CPU_GUARD_ROOT:/data2/FreeToken/wt/e2base1-ordinary-rewind/scripts:/data2/FreeToken/wt/e2base1-ordinary-rewind/python"
  export CUDA_VISIBLE_DEVICES=''
fi
exec "${argv[@]}"
