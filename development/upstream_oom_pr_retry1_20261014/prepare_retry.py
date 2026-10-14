"""Prepare a new inert retry packet, preserving the failed window and its valid baseline."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "upstream_oom_pr_20261014"
REMOTE = "/data2/FreeToken/development/" + ROOT.name
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
reference = OLD / "gpu_evidence/gpu_results/main/SUMMARY.json"
shutil.copyfile(reference, ROOT / "reference_main_SUMMARY.json")
shutil.copyfile(OLD / "gpu_evidence/production.active.json", ROOT / "ACTIVE_SNAPSHOT.json")
for name in ("collect_gpu_evidence.py", "record_stage.py", "seal_window.py"):
    content = (OLD / name).read_text(encoding="utf-8")
    if name == "seal_window.py":
        content = content.replace('REMOTE = "/data2/FreeToken/development/upstream_oom_pr_20261014"',
                                  'REMOTE = "/data2/FreeToken/development/" + ROOT.name')
        content = content.replace('"services": 3, "calls": 10', '"services": 2, "calls": 7')
        content = content.replace('"hard_seconds": 2700', '"hard_seconds": 3600')
    (ROOT / name).write_text(content, encoding="utf-8")
monitor = (ROOT / "monitor_window.py").read_text()
(ROOT / "monitor_window.py").write_text(monitor.replace("/data2/FreeToken/development/upstream_oom_pr_20261014", REMOTE))
manifest_path = ROOT / "restore_e3/SOURCE_MANIFEST.json"
manifest = json.loads(manifest_path.read_text())
manifest["identity"] = "UPSTREAM-OOM-PR-RESTORE-E3-20261014-02"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
approval_path = ROOT / "restore_e3/DEPLOYMENT_APPROVAL.json"
approval = json.loads(approval_path.read_text())
approval.update(approval_id=manifest["identity"],
                run_dir="/data2/FreeToken/runs/production/" + manifest["identity"],
                conditions_met=False, package_source_manifest_sha256=sha(manifest_path),
                user_authority="Pending user acknowledgement for the corrected two-arm retry window")
approval_path.write_text(json.dumps(approval, indent=2) + "\n")
auth = json.loads((OLD / "WINDOW_AUTHORIZATION.json").read_text())
auth.update(authorized=False, independent_controller_review=None, recorded_at=datetime.datetime.now().astimezone().isoformat(),
            window_seconds=3600, measurement_seconds=1500,
            active_snapshot=json.loads((ROOT / "ACTIVE_SNAPSHOT.json").read_text()),
            old_stop_adapter="/data2/FreeToken/development/upstream_oom_pr_20261014/restore_e3/stop_approved_restore.py",
            baseline_main_summary=REMOTE + "/reference_main_SUMMARY.json",
            baseline_main_summary_sha256=sha(ROOT / "reference_main_SUMMARY.json"),
            source_sha256_pins={})
auth["scope"] = {"test_services": 2, "generation_calls": 7, "max_pending_http": 2,
                 "backend_replacements": 1, "restore_services": 1, "restore_sdk_calls": 2}
(ROOT / "WINDOW_PROPOSED.json").write_text(json.dumps(auth, indent=2) + "\n")
print(json.dumps({"authorized": False, "reference_calls_reused": 3, "new_services": 2,
                  "new_calls": 7, "measurement_seconds": 1500, "hard_seconds": 3600}, indent=2))
