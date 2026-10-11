#!/usr/bin/env bash
# R041 cold pair and four warm pairs through the existing owned executor.
# Supply assigned batch and accepted T17 evidence after R036 closes.
set -euo pipefail
if (( $# != 2 )); then
  echo 'usage: batchNN_E2-R041_v3.sh ASSIGNED_BATCH check|run' >&2
  exit 64
fi
[[ "$1" =~ ^[1-9][0-9]*$ ]] || exit 64
[[ "$2" == check || "$2" == run ]] || exit 64
: "${FT_D17_SOURCE_CPU_STAGE:?reviewed source CPU stage required}"
: "${FT_D17_SOURCE_REVIEW:?independent startup review required}"
: "${FT_D17_SOURCE_REVIEW_SHA256:?startup review SHA required}"
: "${FT_D17_REALINPUT28:?sealed real inputs required}"
: "${FT_D17_ACCEPTED_T17:?accepted T17 round.json required}"
: "${FT_D17_INDEPENDENT_REVIEW:?T17 independent review required}"
: "${FT_D17_CANDIDATE_TAG:?accepted E2-base.1 candidate tag required}"
source_root="$FT_D17_SOURCE_CPU_STAGE/source_tools"
argv=(/data2/FreeToken/venv/bin/python -u "$source_root/d17_gpu_gate_runner.py"
  --rid E2-R041-gate-D17 --batch "$1"
  --directory /data2/_shared/runs/ft_rounds/E2-R041-gate-D17
  --cold-control-worktree /data2/FreeToken/wt/e2base
  --realinput28 "$FT_D17_REALINPUT28"
  --accepted-t17 "$FT_D17_ACCEPTED_T17"
  --independent-review "$FT_D17_INDEPENDENT_REVIEW"
  --source-cpu-stage "$FT_D17_SOURCE_CPU_STAGE"
  --source-review "$FT_D17_SOURCE_REVIEW"
  --source-review-sha256 "$FT_D17_SOURCE_REVIEW_SHA256"
  --candidate-tag "$FT_D17_CANDIDATE_TAG")
if [[ "$2" == run ]]; then argv+=(--run); fi
export PYTHONPATH="$source_root:/data2/FreeToken/wt/e2base1-ordinary-rewind/scripts:/data2/FreeToken/wt/e2base1-ordinary-rewind/python"
if [[ "$2" == check ]]; then
  : "${FT_CPU_GUARD_ROOT:?CPU check requires the existing socket guard source directory}"
  export PYTHONPATH="$source_root:$FT_CPU_GUARD_ROOT:/data2/FreeToken/wt/e2base1-ordinary-rewind/scripts:/data2/FreeToken/wt/e2base1-ordinary-rewind/python"
  export CUDA_VISIBLE_DEVICES=''
fi
exec "${argv[@]}"
