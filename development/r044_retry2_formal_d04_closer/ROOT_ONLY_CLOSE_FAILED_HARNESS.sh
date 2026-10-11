#!/usr/bin/env bash
# Root-only formal closure for the terminal R044 retry2 harness failure.
set -euo pipefail
if [[ $# -ne 1 || "$1" != "--root-authorized" ]]; then
  echo "usage: $0 --root-authorized" >&2
  exit 64
fi
RID="E2-R044-night-20261010-retry2"
ROOT="/data2/_shared/runs/ft_rounds"
ROUND="$ROOT/$RID"
ARM="$ROUND/ordinary/B1"
CAPTURE="/data2/FreeToken/runs/dev_D16/$RID"
REVIEW="/data2/FreeToken/runs/dev_T10/reviews/$RID"_actual_terminal_v1/review.json
WRAPPER="/data2/FreeToken/runs/plan_batches/batch149_E2-R044-night-20261010-retry2_python.sh"
FREEZE="/data2/FreeToken/development/r044_capture_path_retry2_20261010/ROOT_SOURCE_FREEZE_RECEIPT_V3.json"
SEAL="/data2/FreeToken/development/night_execution_20261009/R044_RETRY2_EXTERNAL_CAPTURE_READONLY_SEAL_V1.json"
CLEANUP="/data2/FreeToken/development/night_execution_20261009/R044_RETRY2_OWNED_CLEANUP_READBACK_V1.json"
D04="/data2/FreeToken/runs/dev_D04/failed_archive_0e939fa01354/scripts/round_close.py"
APPEND="/data2/FreeToken/runs/dev_D04/failed_archive_0e939fa01354/scripts/round_json_append.py"
die(){ echo "$*" >&2; exit 1; }
hash(){ sha256sum -- "$1" | awk '{print $1}'; }
need(){ [[ -f "$1" && ! -L "$1" ]] || die "not a regular file: $1"; [[ "$(hash "$1")" == "$2" ]] || die "hash mismatch: $1"; }
[[ -d "$ROUND" && -d "$ARM" && ! -L "$ROUND" && ! -L "$ARM" ]] || die "raw round absent"
for p in "$ROUND/round.json" "$ROUND/round_history" "$ROUND/MANIFEST.sha256" "$ROUND/batch.sh" "$ROUND/independent_review.json" "$ROUND/SERVICE_ACTUAL"; do
  [[ ! -e "$p" && ! -L "$p" ]] || die "formal artifact already exists: $p"
done
need "$WRAPPER" "27faf06bc8a8736f4da90462517f767021a3279e4ab123d9540719b3f49776a6"
need "$REVIEW" "f87eeb92bdc3cc3d2fe2c9bd25ee6c43bf0ab95b3bb7352fe17e5de838393632"
need "$FREEZE" "36898fad5b3f2d8a894e1db829da6b8a06cf0c44ab95bff537bdbf582401ce23"
need "$CAPTURE/MANIFEST.sha256" "210294b3ec8e1e87a7818491c9fcc73f6107b39d67eddf0b26dd7a7e5a285ece"
need "$SEAL" "dffff678843a38303a93bc99854bc176c616c20d0bf115e8bd5fed2b450b644e"
need "$CLEANUP" "a173864ae95d671172cce611fb26fadf843bca2563166b78ed648c5bc4378b78"
need "$D04" "db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b"
need "$APPEND" "67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"
need "$ROUND/preflight.json" "ffd158109cff10ab71c1050188b3fe0956c865bde41b807e0385da4ed8206c21"
need "$ARM/service_plan.json" "18272ede9f1de4155aa8d610e919dcc0f223d50e1ab72e75409ebd8780b283c6"
need "$ARM/SERVE_CMD.txt" "4866c5c683a785ae0a41bf144973a6f50fa8d2e025f58525745a9d6ea6a6d8d6"
need "$ARM/serve.log" "27e1be50d056383fcf598e260b87e3149cdefd255938479c4a20ad6e6bc46940"
need "$ROUND/failed_harness.json" "483236a1c425d52cafb14567fa6a2ea0d5e689ea69a89c01107f121ca64fdaa1"
need "$ROUND/owned_cleanup.json" "47a120be09bda67ccbcb83b4faeedbf51f4ea07aa71d5dbac9ccb914a95158b7"
need "$ROOT/batch149.log" "5e4b10cb892f57b94eb892a2c028ed4d1fc51189d0edb24a58770972dd9bf4b8"
need "$CAPTURE/ordinary/B1/capture/service_delivery.json" "3431bb15ce8029e758189ec79105b1bb43cfd3ddcfbe431f351712687d07a88f"
need "$CAPTURE/ordinary/B1/capture/sampler/manifest.json" "52398070057f4a8392243a550ef601be07aafbe3e4427285be400c8e4146cd8d"

tmp="$(mktemp -d)"
created=()
phase="prepare"
cleanup() {
  local code=$?
  if [[ "$phase" == "prepare" ]]; then
    for p in "\${created[@]:-}"; do
      [[ -e "$p" || -L "$p" ]] || continue
      chmod u+w -- "$p" 2>/dev/null || true
      rm -rf -- "$p"
    done
  fi
  rm -rf -- "$tmp"
  exit "$code"
}
trap cleanup EXIT

python3 -B - "$ARM/service_plan.json" "$ARM/serve.log" "$tmp/serve_args.txt" "$tmp/ENV.txt" "$tmp/round.json" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
plan_path,log_path,args_out,env_out,round_out=map(Path,sys.argv[1:])
plan=json.loads(plan_path.read_text(encoding="utf-8"))
argv,env=plan.get("argv"),plan.get("environment")
if not isinstance(argv,list) or not argv or not all(isinstance(v,str) and v for v in argv): raise SystemExit("invalid argv")
if not isinstance(env,dict) or not env or not all(isinstance(k,str) and isinstance(v,str) for k,v in env.items()): raise SystemExit("invalid env")
match=re.search(r"Parsed arguments:\n(ServerArgs\([^\n]+\))",log_path.read_text(encoding="utf-8",errors="strict"))
if not match: raise SystemExit("missing exact ServerArgs line")
args_out.write_text(match.group(1)+"\n",encoding="utf-8")
env_out.write_text(json.dumps(env,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rid="E2-R044-night-20261010-retry2"
round_root="/data2/_shared/runs/ft_rounds/"+rid
cap="/data2/FreeToken/runs/dev_D16/"+rid
doc={
 "schema":"ft_round/v2","round_id":rid,"card":"T10","batch":149,
 "base":{"commit":"0aa23431e5b800797543bdecbf35a01045131d7d"},
 "experimental":{"candidate_commit":"0aa23431e5b800797543bdecbf35a01045131d7d"},
 "retry_of":"E2-R044-night-20261009","retry_index":2,
 "actual_services":1,"actual_generation_calls":24,"physical_delivery_tokens":3581,
 "t10_measurement_accepted":False,"product_acceptance":False,
 "proposed_verdict":"failed_harness","verdict":"pending_review","verdict_history":[],"retractions":[],
 "batch_logs":[{"path":"/data2/_shared/runs/ft_rounds/batch149.log","sha256":"5e4b10cb892f57b94eb892a2c028ed4d1fc51189d0edb24a58770972dd9bf4b8"}],
 "launch_receipt":{"path":"/data2/_shared/runs/ft_rounds/launch_E2-R044-night-20261010-retry2_batch149.json","sha256":"09761b0f4377ba5e540b8c940caafc4ab40013aa1caaacc6da2ffec65b504da6"},
 "formal_batch":{"path":"batch.sh","sha256":"27faf06bc8a8736f4da90462517f767021a3279e4ab123d9540719b3f49776a6"},
 "independent_review":{"path":"independent_review.json","sha256":"f87eeb92bdc3cc3d2fe2c9bd25ee6c43bf0ab95b3bb7352fe17e5de838393632"},
 "source_provenance":{"root_freeze_path":"/data2/FreeToken/development/r044_capture_path_retry2_20261010/ROOT_SOURCE_FREEZE_RECEIPT_V3.json","root_freeze_sha256":"36898fad5b3f2d8a894e1db829da6b8a06cf0c44ab95bff537bdbf582401ce23","source_rows":24,"raw_source_copy_root":round_root+"/source"},
 "serve":{"arms":{"SERVICE_ACTUAL":{"raw_source":round_root+"/ordinary/B1","service_plan_sha256":H(plan_path),"canonical_metadata":{"SERVE_CMD.txt":"4866c5c683a785ae0a41bf144973a6f50fa8d2e025f58525745a9d6ea6a6d8d6","serve.log":"27e1be50d056383fcf598e260b87e3149cdefd255938479c4a20ad6e6bc46940","serve_args.txt":H(args_out),"ENV.txt":H(env_out)}}}},
 "result_binding":{"preflight.json":{"path":"preflight.json","sha256":"ffd158109cff10ab71c1050188b3fe0956c865bde41b807e0385da4ed8206c21"},"failed_harness.json":{"path":"failed_harness.json","sha256":"483236a1c425d52cafb14567fa6a2ea0d5e689ea69a89c01107f121ca64fdaa1"},"owned_cleanup.json":{"path":"owned_cleanup.json","sha256":"47a120be09bda67ccbcb83b4faeedbf51f4ea07aa71d5dbac9ccb914a95158b7"}},
 "failure_classification":{"service_terminal":"failed_harness","reason":"actual ServerArgs lacks strict max_prefill_length key although the service plan contains --max-prefill-length; no UID is missing","admission_uids":24,"delivery_uids":24,"uid_range":"0..23","missing_uids":0,"service_delivery_errors":0},
 "external_capture":{"absolute_capture_tree":cap+"/ordinary/B1/capture","sealed_tree_root":cap,"manifest_path":cap+"/MANIFEST.sha256","manifest_sha256":"210294b3ec8e1e87a7818491c9fcc73f6107b39d67eddf0b26dd7a7e5a285ece","manifest_member_files":7252,"manifest_member_bytes":4490523098,"manifest_self_excluded":True,"all_readonly":True,"seal_receipt_path":"/data2/FreeToken/development/night_execution_20261009/R044_RETRY2_EXTERNAL_CAPTURE_READONLY_SEAL_V1.json","seal_receipt_sha256":"dffff678843a38303a93bc99854bc176c616c20d0bf115e8bd5fed2b450b644e","service_delivery_sha256":"3431bb15ce8029e758189ec79105b1bb43cfd3ddcfbe431f351712687d07a88f","sampler_manifest_sha256":"52398070057f4a8392243a550ef601be07aafbe3e4427285be400c8e4146cd8d"},
 "terminal_cleanup":{"path":"/data2/FreeToken/development/night_execution_20261009/R044_RETRY2_OWNED_CLEANUP_READBACK_V1.json","sha256":"a173864ae95d671172cce611fb26fadf843bca2563166b78ed648c5bc4378b78","cleanup_ok":True,"gpu_compute_absent":True,"gpu_lock_absent":True},
 "closure_tools":{"round_close_sha256":"db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b","round_json_append_sha256":"67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"}
}
round_out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
PY

mkdir "$ROUND/SERVICE_ACTUAL"; created+=("$ROUND/SERVICE_ACTUAL")
install -m 0444 -- "$WRAPPER" "$ROUND/batch.sh"; created+=("$ROUND/batch.sh")
install -m 0444 -- "$REVIEW" "$ROUND/independent_review.json"; created+=("$ROUND/independent_review.json")
install -m 0444 -- "$ARM/SERVE_CMD.txt" "$ROUND/SERVICE_ACTUAL/SERVE_CMD.txt"; created+=("$ROUND/SERVICE_ACTUAL/SERVE_CMD.txt")
install -m 0444 -- "$ARM/serve.log" "$ROUND/SERVICE_ACTUAL/serve.log"; created+=("$ROUND/SERVICE_ACTUAL/serve.log")
install -m 0444 -- "$tmp/serve_args.txt" "$ROUND/SERVICE_ACTUAL/serve_args.txt"; created+=("$ROUND/SERVICE_ACTUAL/serve_args.txt")
install -m 0444 -- "$tmp/ENV.txt" "$ROUND/SERVICE_ACTUAL/ENV.txt"; created+=("$ROUND/SERVICE_ACTUAL/ENV.txt")
install -m 0444 -- "$tmp/round.json" "$ROUND/round.json"; created+=("$ROUND/round.json")

phase="formal"
python3 -B "$D04" "$RID" --round-root "$ROOT"
python3 -B "$APPEND" "$ROUND" verdict --new failed_harness --by root --reason "strict actual ServerArgs lacks max_prefill_length; raw measurement preserved but not accepted and no UID is missing" --evidence "$ROUND/failed_harness.json" "$ROUND/independent_review.json" "$CAPTURE/MANIFEST.sha256" "$SEAL" "$CLEANUP"
python3 -B "$APPEND" "$ROUND" check
phase="complete"
echo "R044 retry2 D04 failed_harness closure complete: $ROUND"
