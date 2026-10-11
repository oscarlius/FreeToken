#!/usr/bin/env bash
# Root-only formal D04 closer for the already-terminal R044 retry1 failure.
# It starts no process, does not touch the capture tree, and never copies FP32
# capture bytes; it only binds the external sealed manifest.
set -euo pipefail

if [[ $# -ne 1 || "$1" != "--root-authorized" ]]; then
  echo "usage: $0 --root-authorized" >&2
  exit 64
fi

RID="E2-R044-night-20261010-retry1"
ROOT="/data2/_shared/runs/ft_rounds"
ROUND="$ROOT/$RID"
ARM="$ROUND/ordinary/B1"
CANONICAL_ARM="$ROUND/SERVICE_ACTUAL"
WRAPPER="/data2/FreeToken/runs/plan_batches/batch147_E2-R044-night-20261010-retry1_python.sh"
INDEPENDENT_REVIEW="/data2/FreeToken/runs/dev_T10/reviews/$RID"_actual_terminal_v1/review.json
EXTERNAL_MANIFEST="/data2/FreeToken/runs/dev_D16/$RID/MANIFEST.sha256"
EXTERNAL_SEAL="/data2/FreeToken/development/night_execution_20261009/R044_RETRY1_EXTERNAL_CAPTURE_READONLY_SEAL_V1.json"
CLEANUP_READBACK="/data2/FreeToken/development/night_execution_20261009/R044_RETRY1_OWNED_CLEANUP_READBACK_V1.json"
D04_CLOSE="/data2/FreeToken/runs/dev_D04/failed_archive_0e939fa01354/scripts/round_close.py"
ROUND_APPEND="/data2/FreeToken/runs/dev_D04/failed_archive_0e939fa01354/scripts/round_json_append.py"

readonly WRAPPER_SHA="df2ce08320f14e9932c8d1016b862ded502a124669267c9309f9554c444c082d"
readonly REVIEW_SHA="2c94516f7610389667088787821271ed4401e805a594ebfdea8e42ec2ad28a0e"
readonly EXTERNAL_MANIFEST_SHA="2c79bb40083c0145f6b61331bdf3450ff48c62d52a0ad608048f4b99bca78629"
readonly EXTERNAL_SEAL_SHA="44bd77e005656baa2b2595d8ae85afd3083eeece65ae67659a174a8c9bdd804f"
readonly CLEANUP_SHA="663882719726b8cab23f96eb25c6766f05917a44a515524e47b2ffb96eee5e19"
readonly D04_CLOSE_SHA="db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b"
readonly ROUND_APPEND_SHA="67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"
readonly PREFLIGHT_SHA="db19c36211f33810de3a428d052ce1ee513877ed500c380ef198ecd13344cb75"
readonly SERVICE_PLAN_SHA="efc8c124ae110da78aed94f0f3977b19496158bbcdf712ddd60d72e8f4bd895b"
readonly SERVE_CMD_SHA="d40082bf4c099680ea965b8b5084552925dfec2e841317473784338bb961a1dd"
readonly SERVE_LOG_SHA="ef5fffb6c04303891a39117e4ce637107e98ae50acf7b826de2cfa9749103506"
readonly FAILED_SHA="613de2c27281abe1625f7dc8f920c400ebcab0d3a584281b030ceba90c30e6b3"
readonly OWNED_CLEANUP_SHA="089f2857df4bbe6df6b5197ef475277e1eb10d33083c82421bee14013e4565b7"
readonly BATCH_LOG_SHA="cd29036e80e24e1a31f21a7b58c552b291b177de5d5d1d6632dd887a68454d49"
readonly SERVICE_DELIVERY_SHA="a9a406654e87b3d5cb524b148e27ae2627e4a020095f755704651f6417967460"
readonly SAMPLER_SHA="467e6e26212fa866ec670e2af4cd0c694940299e21ab8d94e002d68563e67016"

die() { echo "R044 D04 closer: $*" >&2; exit 1; }
digest() { sha256sum -- "$1" | awk '{print $1}'; }
require_regular_hash() {
  local path="$1" expected="$2"
  [[ -f "$path" && ! -L "$path" ]] || die "required regular file missing: $path"
  [[ "$(digest "$path")" == "$expected" ]] || die "hash mismatch: $path"
}

[[ -d "$ROUND" && ! -L "$ROUND" && -d "$ARM" && ! -L "$ARM" ]] || die "raw round or service arm is unavailable"
for path in "$ROUND/round.json" "$ROUND/round_history" "$ROUND/MANIFEST.sha256" "$ROUND/batch.sh" "$ROUND/independent_review.json" "$CANONICAL_ARM"; do
  [[ ! -e "$path" && ! -L "$path" ]] || die "formal round already has $path"
done

require_regular_hash "$WRAPPER" "$WRAPPER_SHA"
require_regular_hash "$INDEPENDENT_REVIEW" "$REVIEW_SHA"
require_regular_hash "$EXTERNAL_MANIFEST" "$EXTERNAL_MANIFEST_SHA"
require_regular_hash "$EXTERNAL_SEAL" "$EXTERNAL_SEAL_SHA"
require_regular_hash "$CLEANUP_READBACK" "$CLEANUP_SHA"
require_regular_hash "$D04_CLOSE" "$D04_CLOSE_SHA"
require_regular_hash "$ROUND_APPEND" "$ROUND_APPEND_SHA"
require_regular_hash "$ROUND/preflight.json" "$PREFLIGHT_SHA"
require_regular_hash "$ARM/service_plan.json" "$SERVICE_PLAN_SHA"
require_regular_hash "$ARM/SERVE_CMD.txt" "$SERVE_CMD_SHA"
require_regular_hash "$ARM/serve.log" "$SERVE_LOG_SHA"
require_regular_hash "$ROUND/failed_harness.json" "$FAILED_SHA"
require_regular_hash "$ROUND/owned_cleanup.json" "$OWNED_CLEANUP_SHA"
require_regular_hash "$ROOT/batch147.log" "$BATCH_LOG_SHA"
require_regular_hash "/data2/FreeToken/runs/dev_D16/$RID/ordinary/B1/capture/service_delivery.json" "$SERVICE_DELIVERY_SHA"
require_regular_hash "/data2/FreeToken/runs/dev_D16/$RID/ordinary/B1/capture/sampler/manifest.json" "$SAMPLER_SHA"

tmp="$(mktemp -d)"
created=()
phase="prepare"
cleanup() {
  local code=$?
  if [[ "$phase" == "prepare" ]]; then
    for path in "${created[@]:-}"; do
      [[ -e "$path" || -L "$path" ]] || continue
      chmod u+w -- "$path" 2>/dev/null || true
      rm -rf -- "$path"
    done
  fi
  rm -rf -- "$tmp"
  exit "$code"
}
trap cleanup EXIT

# Extract only the observed ServerArgs line from the immutable service log and
# serialize only the recorded service-plan environment.  These canonical files
# are provenance-derived metadata, not a replay or a new observation.
python3 -B - "$ARM/service_plan.json" "$ARM/serve.log" "$tmp/serve_args.txt" "$tmp/ENV.txt" "$tmp/round.json" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

plan_path, log_path, args_out, env_out, round_out = map(Path, sys.argv[1:])
plan = json.loads(plan_path.read_text(encoding="utf-8"))
argv, env = plan.get("argv"), plan.get("environment")
if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
    raise SystemExit("service_plan argv is not a non-empty string list")
if not isinstance(env, dict) or not env or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
    raise SystemExit("service_plan environment is not a string map")
text = log_path.read_text(encoding="utf-8", errors="strict")
match = re.search(r"Parsed arguments:\n(ServerArgs\([^\n]+\))", text)
if not match:
    raise SystemExit("serve.log has no exact Parsed arguments ServerArgs line")
args_out.write_text(match.group(1) + "\n", encoding="utf-8")
env_out.write_text(json.dumps(env, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
H = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rid = "E2-R044-night-20261010-retry1"
root = "/data2/_shared/runs/ft_rounds/" + rid
capture_root = "/data2/FreeToken/runs/dev_D16/" + rid
doc = {
  "schema": "ft_round/v2", "round_id": rid, "card": "T10", "batch": 147,
  "base": {"commit": "0aa23431e5b800797543bdecbf35a01045131d7d"},
  "experimental": {"candidate_commit": "0aa23431e5b800797543bdecbf35a01045131d7d"},
  "retry_of": "E2-R044-night-20261009", "retry_index": 1,
  "actual_services": 1, "actual_generation_calls": 24, "physical_delivery_tokens": 3581,
  "t10_measurement_accepted": False, "product_acceptance": False,
  "proposed_verdict": "failed_harness", "verdict": "pending_review",
  "verdict_history": [], "retractions": [],
  "batch_logs": [{"path": "/data2/_shared/runs/ft_rounds/batch147.log", "sha256": "cd29036e80e24e1a31f21a7b58c552b291b177de5d5d1d6632dd887a68454d49"}],
  "launch_receipt": {"path": "/data2/_shared/runs/ft_rounds/launch_E2-R044-night-20261010-retry1_batch147.json", "sha256": "6645dc9f3696914a450e1b8a8d12fae980b6c6fc0d269eb9c6de5da257459c2b"},
  "formal_batch": {"path": "batch.sh", "sha256": "df2ce08320f14e9932c8d1016b862ded502a124669267c9309f9554c444c082d"},
  "independent_review": {"path": "independent_review.json", "sha256": "2c94516f7610389667088787821271ed4401e805a594ebfdea8e42ec2ad28a0e"},
  "serve": {"arms": {"SERVICE_ACTUAL": {"raw_source": root + "/ordinary/B1", "service_plan_sha256": H(plan_path), "canonical_metadata": {"SERVE_CMD.txt": "d40082bf4c099680ea965b8b5084552925dfec2e841317473784338bb961a1dd", "serve.log": "ef5fffb6c04303891a39117e4ce637107e98ae50acf7b826de2cfa9749103506", "serve_args.txt": H(args_out), "ENV.txt": H(env_out)}}}},
  "result_binding": {"preflight.json": {"path": "preflight.json", "sha256": "db19c36211f33810de3a428d052ce1ee513877ed500c380ef198ecd13344cb75"}, "failed_harness.json": {"path": "failed_harness.json", "sha256": "613de2c27281abe1625f7dc8f920c400ebcab0d3a584281b030ceba90c30e6b3"}, "owned_cleanup.json": {"path": "owned_cleanup.json", "sha256": "089f2857df4bbe6df6b5197ef475277e1eb10d33083c82421bee14013e4565b7"}},
  "failure_classification": {"service_terminal": "failed", "admission_uids": 24, "delivery_uids": 24, "uid_range": "0..23", "history_indeterminate_errors": 19, "aggregate_indeterminate_errors": 1, "missing_uids": 0, "reason": "physical sampler history missing or out of order; not a missing-UID failure"},
  "external_capture": {"absolute_capture_tree": capture_root + "/ordinary/B1/capture", "sealed_tree_root": capture_root, "manifest_path": capture_root + "/MANIFEST.sha256", "manifest_sha256": "2c79bb40083c0145f6b61331bdf3450ff48c62d52a0ad608048f4b99bca78629", "files": 7214, "bytes": 4470325509, "all_readonly": True, "seal_receipt_path": "/data2/FreeToken/development/night_execution_20261009/R044_RETRY1_EXTERNAL_CAPTURE_READONLY_SEAL_V1.json", "seal_receipt_sha256": "44bd77e005656baa2b2595d8ae85afd3083eeece65ae67659a174a8c9bdd804f", "service_delivery_sha256": "a9a406654e87b3d5cb524b148e27ae2627e4a020095f755704651f6417967460", "sampler_manifest_sha256": "467e6e26212fa866ec670e2af4cd0c694940299e21ab8d94e002d68563e67016"},
  "terminal_cleanup": {"path": "/data2/FreeToken/development/night_execution_20261009/R044_RETRY1_OWNED_CLEANUP_READBACK_V1.json", "sha256": "663882719726b8cab23f96eb25c6766f05917a44a515524e47b2ffb96eee5e19", "cleanup_ok": True, "gpu_compute_absent": True, "gpu_lock_absent": True},
  "closure_tools": {"round_close_sha256": "db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b", "round_json_append_sha256": "67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"}
}
round_out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

mkdir "$CANONICAL_ARM"; created+=("$CANONICAL_ARM")
install -m 0444 -- "$WRAPPER" "$ROUND/batch.sh"; created+=("$ROUND/batch.sh")
install -m 0444 -- "$INDEPENDENT_REVIEW" "$ROUND/independent_review.json"; created+=("$ROUND/independent_review.json")
install -m 0444 -- "$ARM/SERVE_CMD.txt" "$CANONICAL_ARM/SERVE_CMD.txt"; created+=("$CANONICAL_ARM/SERVE_CMD.txt")
install -m 0444 -- "$ARM/serve.log" "$CANONICAL_ARM/serve.log"; created+=("$CANONICAL_ARM/serve.log")
install -m 0444 -- "$tmp/serve_args.txt" "$CANONICAL_ARM/serve_args.txt"; created+=("$CANONICAL_ARM/serve_args.txt")
install -m 0444 -- "$tmp/ENV.txt" "$CANONICAL_ARM/ENV.txt"; created+=("$CANONICAL_ARM/ENV.txt")
install -m 0444 -- "$tmp/round.json" "$ROUND/round.json"; created+=("$ROUND/round.json")

phase="formal"
python3 -B "$D04_CLOSE" "$RID" --round-root "$ROOT"
python3 -B "$ROUND_APPEND" "$ROUND" verdict --new failed_harness --by root \
  --reason "24 SSE calls completed but 19 physical sampler history errors plus one aggregate indeterminate observer error invalidate the capture; no UID is missing" \
  --evidence "$ROUND/failed_harness.json" "$ROUND/independent_review.json" "$EXTERNAL_MANIFEST" "$EXTERNAL_SEAL" "$CLEANUP_READBACK"
python3 -B "$ROUND_APPEND" "$ROUND" check

phase="complete"
echo "R044 retry1 formal D04 failed_harness closure complete: $ROUND"

