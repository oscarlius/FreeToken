"""Read-only local preparation for the authorized OOM GPU window.

This never starts/stops a service or acquires the GPU lock.  It intentionally writes an
unauthorized packet; only the root-controlled authorization document can permit --run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESTORE_ID = "UPSTREAM-OOM-PR-RESTORE-E3-20261014-01"
ADAPTERS = (
    "approved_attempt.py", "start_approved_release.py", "wait_release_and_smoke.py",
    "run_exclusive_smoke.py", "stop_approved_restore.py", "deploy_conditional.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> dict:
    auth = ROOT / "WINDOW_AUTHORIZATION.json"
    if auth.exists():
        raise RuntimeError("authorization already exists; preparation will not replace it")
    restore = ROOT / "restore_e3"
    restore.mkdir(exist_ok=True)
    source = ROOT.parent / "upstream_layer_major_pr_20261014" / "restore_e3"
    guard_source = ROOT.parent / "upstream_layer_major_pr_20261014" / "recovery_guard.py"
    guard_target = ROOT / "recovery_guard.py"
    if not guard_source.is_file() or guard_target.exists():
        raise RuntimeError("missing or already-staged recovery_guard.py")
    guard_target.write_bytes(guard_source.read_bytes())
    files = {}
    for name in ADAPTERS:
        path = source / name
        if not path.is_file():
            raise RuntimeError(f"missing frozen restore adapter: {path}")
        target = restore / name
        if target.exists():
            raise RuntimeError(f"restore target already exists: {target}")
        target.write_bytes(path.read_bytes())
        files[name] = digest(target)
    manifest = {"identity": RESTORE_ID, "files": files, "conditions_met": False}
    (restore / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    original = source / "DEPLOYMENT_APPROVAL.json"
    if not original.is_file():
        raise RuntimeError(f"missing frozen restore approval: {original}")
    approval = json.loads(original.read_text())
    approval.update({
        "approval_id": RESTORE_ID,
        "run_dir": f"/data2/FreeToken/runs/production/{RESTORE_ID}",
        "conditions_met": False,
        "user_authority": "Pending explicit user acknowledgement for UPSTREAM-OOM-PR-RESTORE-E3-20261014-01",
        "scope": [
            "One authorized E3 restoration after the upstream OOM PR GPU window",
            "One start and one smoke only; no observer or retry",
        ],
        "source_manifest_original_sha256": digest(source / "SOURCE_MANIFEST.json"),
        "package_source_manifest_sha256": digest(restore / "SOURCE_MANIFEST.json"),
    })
    (restore / "DEPLOYMENT_APPROVAL.json").write_text(json.dumps(approval, indent=2) + "\n")
    packet = {
        "authorized": False,
        "source_approval": False,
        "restore_identity": RESTORE_ID,
        "client": "gpu_http_check.py",
        "arms": ["main", "candidate_off", "candidate_on"],
        "measurement_seconds": 1800,
        "window_seconds": 2700,
    }
    (ROOT / "GPU_WINDOW_PACKET.json").write_text(json.dumps(packet, indent=2) + "\n")
    return packet


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
