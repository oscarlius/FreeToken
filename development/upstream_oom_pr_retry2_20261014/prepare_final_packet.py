"""Prepare an inert final one-arm GPU packet bound to the corrected contribution SHA."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "upstream_oom_pr_retry1_20261014"
ORIGINAL = ROOT.parent / "upstream_oom_pr_20261014"
REMOTE = "/data2/FreeToken/development/" + ROOT.name
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
shutil.copyfile(OLD / "gpu_evidence/production.active.json", ROOT / "ACTIVE_SNAPSHOT.json")
for name in ("monitor_window.py", "collect_gpu_evidence.py", "record_stage.py", "seal_window.py", "stage_retry.py"):
    content = (OLD / name).read_text(encoding="utf-8")
    content = content.replace("upstream_oom_pr_retry1_20261014", "upstream_oom_pr_retry2_20261014")
    if name == "seal_window.py":
        content = content.replace('"services": 2, "calls": 7', '"services": 1, "calls": 4')
        content = content.replace('"GPU_CPU_PREFLIGHT.json", "GPU_CPU_PREFLIGHT_CLOSEOUT.json"', '"GPU_CPU_PREFLIGHT.json"')
        content = content.replace("INDEPENDENT_RETRY1_REVIEW_20261014.md", "INDEPENDENT_RETRY2_REVIEW_20261014.md")
    if name == "stage_retry.py":
        content = content.replace("GPU_CPU_PREFLIGHT_CLOSEOUT.json", "GPU_CPU_PREFLIGHT.json")
        content = content.replace("import datetime,hashlib,importlib.util,json,os,pathlib,subprocess", "import datetime,hashlib,importlib.util,json,os,pathlib,subprocess,shutil")
        content = content.replace("m.verify_pins(auth);package=", """for name,digest in auth['native_modules'].items():
 source=pathlib.Path(auth['main_source'])/name;target=pathlib.Path(auth['candidate_source'])/name
 assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
 if target.exists():assert target.read_bytes()==source.read_bytes()
 else:shutil.copyfile(source,target)
m.verify_pins(auth);package=""")
    (ROOT / name).write_text(content, encoding="utf-8")
manifest_path = ROOT / "restore_e3/SOURCE_MANIFEST.json"
manifest = json.loads(manifest_path.read_text())
manifest["identity"] = "UPSTREAM-OOM-PR-RESTORE-E3-20261014-03"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
approval_path = ROOT / "restore_e3/DEPLOYMENT_APPROVAL.json"
approval = json.loads(approval_path.read_text())
approval.update(approval_id=manifest["identity"], run_dir="/data2/FreeToken/runs/production/" + manifest["identity"],
                conditions_met=False, package_source_manifest_sha256=sha(manifest_path),
                user_authority="Pending acknowledgement for final one-arm OOM validation")
approval_path.write_text(json.dumps(approval, indent=2) + "\n")
auth = json.loads((OLD / "WINDOW_AUTHORIZATION.json").read_text())
auth.update(authorized=False, independent_controller_review=None,
            active_snapshot=json.loads((ROOT / "ACTIVE_SNAPSHOT.json").read_text()),
            old_stop_adapter="/data2/FreeToken/development/upstream_oom_pr_retry1_20261014/restore_e3/stop_approved_restore.py",
            baseline_main_summary=REMOTE + "/reference_main_SUMMARY.json",
            baseline_main_summary_sha256=sha(ROOT / "reference_main_SUMMARY.json"),
            candidate_source="/data2/FreeToken/development/upstream_oom_pr_20261014/candidate_oom_final",
            candidate_archive="/data2/FreeToken/development/upstream_oom_pr_20261014/candidate_oom_final.zip",
            candidate_commit="a4ebbfda742fbad1df240621647014a39c70acd6", source_sha256_pins={})
auth["scope"] = {"test_services": 1, "generation_calls": 4, "max_pending_http": 2,
                 "backend_replacements": 1, "restore_services": 1, "restore_sdk_calls": 2}
(ROOT / "WINDOW_PROPOSED.json").write_text(json.dumps(auth, indent=2) + "\n")
for name in ("candidate_oom_final.receipt.json", "candidate_oom_final.stdout.log"):
    shutil.copyfile(ORIGINAL / name, ROOT / name)
publish = ROOT / "publish_pr.py"
publish.write_text(publish.read_text().replace("eb9e70f30ed7a714ce9918ff905e86d2628bc126", auth["candidate_commit"]))
print(json.dumps({"authorized": False, "candidate": auth["candidate_commit"], "services": 1, "calls": 4}))
