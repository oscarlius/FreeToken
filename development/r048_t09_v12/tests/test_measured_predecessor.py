import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def entry(tmp_path, monkeypatch):
    path = Path(os.environ.get("FT_ENTRY_UNDER_TEST", Path(__file__).parents[1] / "r048_t09_prepare_v12.py"))
    spec = importlib.util.spec_from_file_location("t09_prerequisite_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    rounds = tmp_path / "rounds"
    (rounds / "E2-R049b").mkdir(parents=True)
    gate = tmp_path / "candidate_gate.json"
    gate.write_text(json.dumps({"experimental": {"candidate_commit": module.CANDIDATE}, "base": {"commit": module.BASE}}))
    monkeypatch.setattr(module, "git", lambda args: module.CANDIDATE if "rev-parse" in args else "")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(module, "DRY_RUN", tmp_path / "dry_run")
    if hasattr(module, "queue_exception"):
        original_exception = module.queue_exception
        monkeypatch.setattr(module, "queue_exception", lambda: original_exception(rounds))
    return module, worktree, gate


def admit(entry, status, monkeypatch):
    module, worktree, gate = entry
    calls = []

    def closed(rid, required):
        calls.append((rid, required))
        if rid == "E2-R049b" and status != required:
            raise RuntimeError("R049b failed metadata is not closed")
        return gate

    original = module.admission
    monkeypatch.setattr(module, "load_d07", lambda: SimpleNamespace(require_closed_round=closed))
    monkeypatch.setattr(module, "admission", lambda require_round=closed: original(require_round=require_round, worktree=worktree, lock=worktree / "gpu.lock"))
    return module, calls


def test_existing_failed_round_is_metadata_only(entry, monkeypatch):
    module, calls = admit(entry, "failed_harness", monkeypatch)
    receipt = module.admission()
    assert ("E2-R049b", "failed_harness") in calls
    assert "E2-R049b" not in receipt["closures"]
    assert "E2-R049b" in receipt["failed_metadata"]
    assert ("E2-R051a-gate-D08", "kept") in calls
    assert receipt["queue_exception"] == module.QUEUE_EXCEPTION
    assert receipt["queue_exception"]["no_data_dependency"] is True


@pytest.mark.parametrize("status", [None, "measured"])
def test_wrong_failed_metadata_rejected_before_filedry_writes(entry, monkeypatch, status):
    module, _ = admit(entry, status, monkeypatch)
    with pytest.raises(RuntimeError, match="R049b failed metadata is not closed"):
        module.prepare(module.DRY_RUN)
    assert not module.DRY_RUN.exists()
