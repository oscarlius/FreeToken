import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def entry(tmp_path, monkeypatch):
    path = Path(os.environ.get("FT_ENTRY_UNDER_TEST", Path(__file__).parents[1] / "r052_t11_followup_prepare.py"))
    spec = importlib.util.spec_from_file_location("t11_prerequisite_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rounds = tmp_path / "rounds"
    (rounds / "E2-R045").mkdir(parents=True)
    monkeypatch.setattr(module, "ROUNDS", rounds)
    if hasattr(module, "queue_exception"):
        original_exception = module.queue_exception
        monkeypatch.setattr(module, "queue_exception", lambda: original_exception(rounds))
    return module, tmp_path


def dependencies(entry, status, monkeypatch):
    module, root = entry
    calls = []

    def closed(rid, required):
        calls.append((rid, required))
        if rid == "E2-R045" and status != required:
            raise RuntimeError("R045 is not measured")
        return root / rid / "round.json"

    dep = SimpleNamespace(require_r041_kept=lambda _: root / "r041", require_t20_failed_harness=lambda: root / "t20", checked_worktree=lambda _: None, require_closed_round=closed)
    monkeypatch.setattr(module, "load_d07", lambda: dep)
    return module, dep, calls


def test_existing_measured_round_is_accepted(entry, monkeypatch):
    module, dep, calls = dependencies(entry, "measured", monkeypatch)
    receipt = module.admission(dep)
    assert ("E2-R045", "measured") in calls
    assert receipt["r045"].endswith("E2-R045/round.json") or receipt["r045"].endswith("E2-R045\\round.json")
    assert receipt["queue_exception"] is None


@pytest.mark.parametrize("status", [None, "failed_harness"])
def test_unmeasured_round_rejected_before_filedry_writes(entry, monkeypatch, status):
    module, _, _ = dependencies(entry, status, monkeypatch)
    with pytest.raises(RuntimeError, match="R045 is not measured"):
        module.dry_run()
    assert not module.dry_run_directory().exists()
