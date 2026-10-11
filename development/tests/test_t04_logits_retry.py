from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "t04_logits_retry.py"
SPEC = importlib.util.spec_from_file_location("t04_logits_retry_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
retry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retry)


class FakeBase:
    def gate(self, candidate, commit):
        return {"candidate": str(candidate), "commit": commit}


class FakePhase:
    def __init__(self, out):
        self.out = out
        self.base = FakeBase()

    def run(self):
        return self.gate()


def fake_inherited(out):
    return SimpleNamespace(Phase2=lambda args: FakePhase(out))


def test_retry_gate_rejects_any_r014_identity_before_lifecycle_mutation(tmp_path):
    args = argparse.Namespace(rid="E2-R014", candidate_commit="a" * 40, k=32)
    wrapped = retry.RetryPhase2(args, fake_inherited(tmp_path / "E2-R014"))

    with pytest.raises(ValueError, match="E2-R015"):
        wrapped.gate()


def test_controlled_mode_mapping_never_invokes_legacy_capture_cli():
    assert retry.capture_mode("candidate_boundary") == "diagnostic"
    assert retry.capture_mode("restore") == "branch-bank"
    assert retry.capture_mode("recompute") == "fresh"
    assert retry.capture_mode("legal") == "fresh"
    with pytest.raises(ValueError):
        retry.capture_mode("unknown")

    argv = retry.controlled_argv(
        client=Path("controlled.py"),
        base_url="http://127.0.0.1:8095",
        prefix=Path("P21976.json"),
        suffix=Path("X32.json"),
        dump=Path("dump"),
        mode="branch-bank",
    )
    assert "capture" not in argv
    assert argv[1] == "controlled.py"
    assert argv[argv.index("--prefix") + 1] == "P21976.json"
    assert argv[argv.index("--suffix") + 1] == "X32.json"
    assert argv[argv.index("--mode") + 1] == "branch-bank"


def test_archiving_keeps_actual_old_and_new_source_origins_in_manifest(tmp_path):
    wrapped = retry.RetryPhase2(
        argparse.Namespace(rid="E2-R015", candidate_commit="a" * 40, k=32),
        fake_inherited(tmp_path),
    )
    wrapped._archive_retry_sources()

    manifest = (tmp_path / "RUN_MANIFEST.sha256").read_text(encoding="utf-8")
    for name, source in {
        "t04_logits_phase2.py": retry.INHERITED_RUNNER,
        "t04_logits_retry.py": MODULE_PATH,
        "t04_capture_controlled.py": retry.CONTROLLED_CLIENT,
    }.items():
        archived = tmp_path / name
        assert archived.read_bytes() == source.read_bytes()
        assert hashlib.sha256(archived.read_bytes()).hexdigest() in manifest
        assert f"  {name}\n" in manifest


def test_inherited_and_controlled_sources_are_hash_pinned():
    assert retry.sha256(retry.INHERITED_RUNNER) == retry.INHERITED_RUNNER_SHA256
    assert retry.sha256(retry.CONTROLLED_CLIENT) == retry.CONTROLLED_CLIENT_SHA256


def test_existing_round_gate_failure_leaves_all_existing_bytes_and_modes_unchanged(tmp_path):
    existing = tmp_path / "E2-R015"
    existing.mkdir()
    artifact = existing / "sealed.json"
    artifact.write_bytes(b"sealed evidence\n")
    artifact.chmod(0o444)
    before = {path.relative_to(existing): (path.read_bytes(), path.stat().st_mode) for path in existing.rglob("*")}
    wrapped = retry.RetryPhase2(
        argparse.Namespace(rid="E2-R015", candidate_commit="a" * 40, k=32, batch=99),
        fake_inherited(existing),
    )

    with pytest.raises(FileExistsError):
        wrapped.run()

    after = {path.relative_to(existing): (path.read_bytes(), path.stat().st_mode) for path in existing.rglob("*")}
    assert after == before
