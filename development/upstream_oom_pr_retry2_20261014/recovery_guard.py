"""Read-only integrity guard for reusing current E3 recovery controls."""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sources(approval):
    ops = Path(approval["frozen_ops"]["path"])
    archive = ops.parents[2]
    if digest(ops / "binary_manifest.json") != approval["frozen_ops"]["binary_manifest_sha256"]:
        raise RuntimeError("Frozen binary manifest changed")
    source_manifest = archive / "evidence/source_manifest.json"
    if digest(source_manifest) != approval["frozen_ops"]["source_manifest_sha256"]:
        raise RuntimeError("Frozen source manifest changed")
    for name, expected in json.loads(source_manifest.read_text()).items():
        path = archive / "source" / name
        if not path.resolve().is_relative_to((archive / "source").resolve()):
            raise RuntimeError("Source path escaped frozen archive")
        if digest(path) != expected:
            raise RuntimeError("Frozen source changed: " + name)
    return {"binary_manifest_sha256": digest(ops / "binary_manifest.json"),
            "source_manifest_sha256": digest(source_manifest)}


def verify_active(snapshot, active):
    for key in ("approval_id", "commit", "worktree", "run_dir"):
        if snapshot.get(key) != active.get(key):
            raise RuntimeError("Production owner changed: " + key)
    for key in ("supervisor", "service", "gpu_owner"):
        if snapshot.get(key) != active.get(key):
            raise RuntimeError("Production execution identity changed: " + key)
