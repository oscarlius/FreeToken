"""CPU-only, read-only independent audit for sealed R027 raw artifacts.

It never launches/stops a service, takes a GPU lock, or writes remotely.  It sends
this program to host 9 over SSH, with CUDA hidden, and creates the local JSON
receipt once using exclusive creation.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE / "t17_r027_independent_cpu_review.json"

PROGRAM = r'''
import hashlib, json, os, pathlib, stat, sys
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
from pathlib import Path

ROOT = Path("/data2/FreeToken")
RID, BATCH = "E2-R027-diagnostic-T17", 55
ROUND = Path("/data2/_shared/runs/ft_rounds") / RID
FIELDS = ("conv_in", "q", "k", "v", "g", "beta")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def terminal(identity):
    stat_path = Path("/proc") / str(identity["pid"]) / "stat"
    if not stat_path.exists():
        return {"absent": True, "pid": identity["pid"], "start_ticks": identity["start_ticks"]}
    fields = stat_path.read_text().rpartition(") ")[2].split()
    if int(fields[19]) != identity["start_ticks"]:
        raise ValueError("process birth identity changed")
    return {"absent": fields[0] == "Z", "pid": identity["pid"], "start_ticks": identity["start_ticks"], "state": fields[0]}

def aggregate(items):
    # Exact encoding: sorted logical name + NUL + SHA256 + LF, UTF-8, then SHA256.
    payload = "".join(name + "\0" + digest + "\n" for name, digest in sorted(items)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

receipt = json.loads((ROOT / "runs/dev_D14" / ("launch_" + RID + ".json")).read_bytes())
if receipt.get("rid") != RID or receipt.get("batch") != BATCH or receipt.get("state") != "launched":
    raise ValueError("exact R027 launch receipt required")
stage = Path(receipt["source_stage"])
report = json.loads((stage / "cpu_validation.json").read_bytes())
if sha(stage / "cpu_validation.json") != receipt["cpu_stage_sha256"]:
    raise ValueError("CPU stage hash differs from launch receipt")
if report.get("gpu_started") is not False or report["source_files"] != receipt["source_files"]:
    raise ValueError("CPU source report differs")
source_bad = []
frozen = Path(receipt["frozen_runner"]).parent
for name, digest in receipt["source_files"].items():
    for label, path in (("stage", stage / name), ("frozen", frozen / name)):
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222 or sha(path) != digest:
            source_bad.append({"location": label, "name": name})
if source_bad:
    raise ValueError("frozen source binding differs")

status = json.loads((ROUND / "status_batch55.json").read_bytes())
if status.get("state") != "complete_measurements_pending_review":
    raise ValueError("terminal measurement status required")
batch_identity = {"pid": receipt["batch_pid"], "start_ticks": status["batch_start_ticks"]}
if not terminal(batch_identity)["absent"]:
    raise ValueError("batch remains live")
arms = {}
for name in ("numeric_warm", "numeric_cold"):
    arm = ROUND / name
    identity = json.loads((arm / "process_identity.json").read_bytes())
    if json.loads((arm / "stop_identity.json").read_bytes()) != {"terminal": True, **identity}:
        raise ValueError("service stop receipt differs: " + name)
    if not terminal(identity)["absent"]:
        raise ValueError("service remains live: " + name)
    arms[name] = {"identity": identity, "terminal": terminal(identity)}
lock = Path("/data2/_shared/gpu.lock")
if lock.exists() and json.loads(lock.read_bytes()).get("owner") == RID:
    raise ValueError("R027 GPU lock remains")

sys.path.insert(0, str(frozen))
import torch
import t17_prefix_numeric_runner as runner
if torch.cuda.is_initialized():
    raise ValueError("CPU audit initialized CUDA")

def load_capture(arm, uid, device):
    root = arm / "numeric"
    final = json.loads((root / ("final_" + str(uid) + ".json")).read_bytes())
    if final.get("valid") is not True or str(final.get("uid")) != str(uid) or final.get("observed_boundary") != 8192:
        raise ValueError("invalid terminal observer receipt")
    receipt_path = root / final["receipt_file"]
    if receipt_path.is_symlink() or sha(receipt_path) != final["receipt_sha256"]:
        raise ValueError("observer receipt hash differs")
    observed = json.loads(receipt_path.read_bytes())
    if observed.get("uid") != str(uid) or observed.get("absolute_interval") != [512, 8192]:
        raise ValueError("observer interval/UID differs")
    expected_segments = [(512, 4608, 512, 4608), (4608, 8192, 4608, device)]
    got_segments = [(item["absolute_start"], item["absolute_end"], item["cached_tokens"], item["device_tokens"])
                    for item in observed["segments"]]
    if got_segments != expected_segments:
        raise ValueError("segment coordinates differ: " + repr(got_segments))
    h = observed["h"]
    track_absolute = (device - 1) // 64 * 64
    expected_h = {"absolute_boundary": 8192, "target_boundary_row": 3584,
                  "cached_tokens": 4608, "device_tokens": device,
                  "actual_track_boundary_row": track_absolute - 4608,
                  "actual_track_absolute_boundary": track_absolute,
                  "actual_track_h_row": (track_absolute - 4608) // 64,
                  "computed_h_row": 56}
    if any(h.get(key) != value for key, value in expected_h.items()):
        raise ValueError("target h coordinates differ")
    tensors, metadata = {}, {}
    for segment in observed["segments"]:
        for field in FIELDS:
            meta = segment["fields"].get(field)
            if meta is None:
                raise ValueError("missing field " + field)
            path = root / meta["file"]
            tensor = torch.load(path, map_location="cpu", weights_only=True)
            if (path.is_symlink() or sha(path) != meta["sha256"] or list(tensor.shape) != meta["shape"]
                    or str(tensor.dtype) != meta["dtype"] or tensor.shape[1] != segment["absolute_end"] - segment["absolute_start"]):
                raise ValueError("tensor binding differs: " + path.name)
            key = (segment["absolute_start"], field)
            tensors[key], metadata[key] = tensor, meta
    path = root / h["file"]
    tensor = torch.load(path, map_location="cpu", weights_only=True)
    if path.is_symlink() or sha(path) != h["sha256"] or list(tensor.shape) != h["shape"] or str(tensor.dtype) != h["dtype"]:
        raise ValueError("h tensor binding differs")
    tensors[("h", "h")], metadata[("h", "h")] = tensor, h
    return final, observed, tensors, metadata

warm_arm, cold_arm = ROUND / "numeric_warm", ROUND / "numeric_cold"
warm_uid = json.loads((warm_arm / "donor.json").read_bytes())["response"]["uid"]
cold_uid = json.loads((cold_arm / "query.json").read_bytes())["response"]["uid"]
warm_final, warm, warm_tensors, warm_meta = load_capture(warm_arm, warm_uid, 8193)
cold_final, cold, cold_tensors, cold_meta = load_capture(cold_arm, cold_uid, 8257)
comparisons, pairs, warm_hashes, cold_hashes = {}, [], [], []
for key in sorted(warm_tensors, key=str):
    left, right = warm_tensors[key], cold_tensors[key]
    if left.shape != right.shape or left.dtype != right.dtype:
        raise ValueError("comparison shape/dtype differs")
    different = left.contiguous().view(torch.uint8) != right.contiguous().view(torch.uint8)
    if key[0] == "h":
        absolute_rows = []
    else:
        mask = different.reshape(left.shape[0], left.shape[1], -1).any(dim=(0, 2))
        absolute_rows = [int(key[0]) + index for index, changed in enumerate(mask.tolist()) if changed]
    name = "h_8192" if key[0] == "h" else key[1] + "_" + str(key[0])
    comparisons[name] = {"equal": not bool(different.any()), "different_bytes": int(different.sum()),
                         "max_abs": float((left.float() - right.float()).abs().max()),
                         "first_different_absolute_token": absolute_rows[0] if absolute_rows else None,
                         "different_absolute_tokens": len(absolute_rows), "shape": list(left.shape),
                         "dtype": str(left.dtype), "warm_sha256": warm_meta[key]["sha256"],
                         "cold_sha256": cold_meta[key]["sha256"]}
    pairs.append((name, warm_meta[key]["sha256"], cold_meta[key]["sha256"]))
    warm_hashes.append((name, warm_meta[key]["sha256"]))
    cold_hashes.append((name, cold_meta[key]["sha256"]))

case = json.loads((ROUND / "real_inputs.json").read_bytes())["cases"][0]
if sha(ROUND / "real_inputs.json") != receipt["source_files"]["real_inputs.json"]:
    raise ValueError("exact input bytes differ")
raw = runner.artifacts.validate_case({"name": "default-prefix-8192", "length": 8192,
                                       "trace_index": case["trace_index"], "context": case["expected_ngram"]},
                                      cold_arm, warm_arm, tail=65, cold_request="query", hit_request="short",
                                      state_root=warm_arm / "dump")
measured_path = ROUND / "diagnostic_batch55.json"
measured = json.loads(measured_path.read_bytes())
if measured["raw_validator"] != raw:
    raise ValueError("frozen raw validator differs from measured diagnostic")

result = {"schema": "ft_t17_prefix_numeric_independent_cpu_review/v1", "rid": RID, "batch": BATCH,
          "cpu_only": True, "cuda_initialized": torch.cuda.is_initialized(),
          "launch_receipt": receipt, "cpu_stage": {"report_sha256": sha(stage / "cpu_validation.json"),
          "source_count": len(receipt["source_files"]), "source_bad": source_bad}, "status": status,
          "batch_terminal": terminal(batch_identity), "arms": arms,
          "input_binding": {"round_real_inputs_sha256": sha(ROUND / "real_inputs.json"),
                            "receipt_real_inputs_sha256": receipt["source_files"]["real_inputs.json"]},
          "coordinates": {"warm_uid": warm_uid, "cold_uid": cold_uid, "warm_h": warm["h"], "cold_h": cold["h"]},
          "tensor_comparisons": comparisons,
          "aggregate_encoding": "UTF-8 of sorted logical_name + NUL + SHA256 + LF; pair aggregate uses logical_name + NUL + warm SHA256 + NUL + cold SHA256 + LF.",
          "warm_tensor_aggregate_sha256": aggregate(warm_hashes), "cold_tensor_aggregate_sha256": aggregate(cold_hashes),
          "pair_tensor_aggregate_sha256": hashlib.sha256("".join(name + "\0" + warm_sha + "\0" + cold_sha + "\n" for name, warm_sha, cold_sha in sorted(pairs)).encode("utf-8")).hexdigest(),
          "diagnostic_sha256": sha(measured_path), "raw_validator": raw,
          "measurement_binding": {"warm_prefix_equals_measured": measured["warm_prefix"] == {"final": warm_final, "receipt": warm,
                                      "installed": json.loads(next((warm_arm / "numeric").glob("installed_*.json")).read_bytes())},
                                  "cold_prefix_equals_measured": measured["cold_prefix"] == {"final": cold_final, "receipt": cold,
                                      "installed": json.loads(next((cold_arm / "numeric").glob("installed_*.json")).read_bytes())}}}
print(json.dumps(result, sort_keys=True))
'''

if REPORT.exists():
    raise FileExistsError(f"refusing to replace {REPORT}")
result = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "9", "env", "CUDA_VISIBLE_DEVICES=", "PYTHONDONTWRITEBYTECODE=1", "/data2/FreeToken/venv/bin/python", "-"],
    input=PROGRAM.encode("utf-8"), capture_output=True,
)
if result.returncode:
    raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
report = json.loads(result.stdout)
if report["cuda_initialized"]:
    raise RuntimeError("CPU audit initialized CUDA")
with REPORT.open("x", encoding="utf-8") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"report": str(REPORT), "report_sha256": __import__("hashlib").sha256(REPORT.read_bytes()).hexdigest(),
                  "diagnostic_sha256": report["diagnostic_sha256"], "pair_tensor_aggregate_sha256": report["pair_tensor_aggregate_sha256"]}, indent=2))