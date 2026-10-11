import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "r055a_gate_d06_prepare.py"


def load():
    spec = importlib.util.spec_from_file_location("r055a_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_identity_and_formal_runner_use_r055a_suffix():
    module = load()
    assert module.RID == "E2-R055a-gate-D06"
    assert module.base.ASSIGNED_RID == module.RID
    assert module.CandidateRunner.__bases__ == (module.base.CandidateRunner,)


def test_owned_entry_rejects_child_arguments_without_run():
    spec = importlib.util.spec_from_file_location("r055a_owned_test", ROOT / "r055a_owned_launch.py")
    owned = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(owned)
    with pytest.raises(SystemExit):
        owned.main(["--owned-child"])


def test_observer_copy_is_writable_for_instrumentation_then_frozen(tmp_path):
    module = load()
    runner = module.CandidateRunner.__new__(module.CandidateRunner)
    wrapper = runner._freeze_observer(tmp_path)
    observer = tmp_path / "t17_d14_observe.py"
    assert wrapper.is_file()
    assert not (observer.stat().st_mode & 0o222)
    source = observer.read_text(encoding="utf-8")
    assert source.index("def r055a_install_decode_hook") < source.index("def startup")
    assert "dev_slots=[slot], length=int(req.device_len), uid=uid" in source


def test_dry_run_uses_sibling_and_real_copy_path(monkeypatch, tmp_path):
    module = load()
    rounds = tmp_path / "ft_rounds"; rounds.mkdir()
    monkeypatch.setattr(module, "ROUNDS", rounds)
    monkeypatch.setattr(module, "r055_tool_preflight", lambda: {"sealed": True})
    monkeypatch.setitem(module.base._private_protocol.__dict__, "SCR", ROOT / "t16_frozen_helpers_v1")
    monkeypatch.setattr(module.CandidateRunner, "gate", lambda *args: "fixture source identity")
    monkeypatch.setattr(module.CandidateRunner, "compiled_extensions", lambda *args: {"cpu": {"sha256": "native fixture"}})
    monkeypatch.setattr(module, "command", lambda *args, **kwargs: "fixture command metadata")
    monkeypatch.setitem(module.base.base, "command", lambda argv, **kwargs: module.PARENT_COMMIT)
    monkeypatch.setattr(module.CandidateRunner, "lock_take", lambda *args: pytest.fail("dry-run took a lock"))
    monkeypatch.setattr(module.CandidateRunner, "lock_release", lambda *args: pytest.fail("dry-run released a lock"))
    monkeypatch.setattr(module, "_check_worktree", lambda path, commit: {"path": str(path), "head": commit})
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("dry-run started a process"))
    result = module.dry_run()
    target = rounds / ".dryrun_R055a_E2-R055a-gate-D06"
    assert result["dry_run_directory"] == str(target)
    assert result["formal_rid_directory_created"] is False
    assert all(result[key] is False for key in ("service_started", "requests_sent", "gpu_lock_taken", "batch_allocated"))
    assert result["port"] != 8095
    execution = target / "round"
    assert (execution / "PARENT0_b1" / "t17_d14_observe.py").stat().st_mode & 0o222 == 0
    for arm in result["arms"]:
        directory = execution / arm["arm"]
        assert (directory / "cold.json").is_file()
        assert (directory / "state_dump" / "index.jsonl").is_file()
        assert (directory / "ENV.txt").read_text().startswith("20")
        assert "--port" in (directory / "SERVE_CMD.txt").read_text()
        assert "CPU FILE PROBE" in (directory / "serve.log").read_text()
    assert (execution / "candidate_binding.json").is_file()
    assert (execution / "batch.sh").read_bytes() == (target / "batch_file_dry_run.sh").read_bytes()
    assert len(result["arms"]) == 6
    assert (execution / "PAUSE_ON" / "r055_pause_observer.py").is_file()
    receipt = json.loads((target / "dry_run_receipt.json").read_text(encoding="utf-8"))
    assert receipt["rid"] == module.RID
    assert len(receipt["source_sha256"]) >= 9
    assert receipt["owner_path"].endswith("r055a_owned_launch.py")
    assert not (rounds / module.RID).exists()
    assert not ((target / "dry_run_receipt.json").stat().st_mode & 0o222)
    with pytest.raises(RuntimeError, match="already exists"):
        module.dry_run()


def test_owned_admission_requires_r050_and_r041_kept():
    source = (ROOT / "r055a_owned_launch.py").read_text(encoding="utf-8")
    assert 'require_closed_round("E2-R050-gate-D15", "kept")' in source
    assert "g.require_r041_kept(module.ROOT)" in source
    assert "R055-gate-D06" not in source


@pytest.mark.parametrize("drift", [None, "uid", "owner", "source", "service", "passed", "writable"])
def test_startup_review_rejects_dry_receipt_drift(monkeypatch, tmp_path, drift):
    from types import SimpleNamespace
    import hashlib
    spec = importlib.util.spec_from_file_location("r055a_review_test", ROOT / "r055a_owned_launch.py")
    owned = importlib.util.module_from_spec(spec); spec.loader.exec_module(owned)
    legacy = owned._legacy()
    rounds = tmp_path / "rounds"
    legacy.ROOT = tmp_path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(owned, "adapter_module", lambda: SimpleNamespace(ROUNDS=rounds))
    monkeypatch.setattr(owned, "source_hashes", lambda: {"source.py": "a" * 64})
    monkeypatch.setattr(owned.os, "getuid", lambda: 1000, raising=False)
    path = rounds / f".dryrun_R055a_{owned.RID}" / "dry_run_receipt.json"
    path.parent.mkdir(parents=True)
    dry = {"schema": "ft_r055a_dry_run/v2", "rid": owned.RID, "passed": True,
           "cwd": str(tmp_path), "owner_path": str(Path(owned.__file__).resolve()),
           "adapter_path": str((owned.HERE / owned.ADAPTER).resolve()),
           "formal_directory": str(rounds / owned.RID), "source_sha256": owned.source_hashes(),
           "user": {"uid": 1000, "user": owned.os.environ.get("USER")},
           "worktrees": {"parent": {"head": legacy.PARENT_COMMIT}, "candidate": {"head": legacy.CANDIDATE_COMMIT}},
           **{name: False for name in ("service_started", "requests_sent", "gpu_lock_taken", "batch_allocated", "formal_rid_directory_created")}}
    if drift == "uid": dry["user"]["uid"] = 999
    elif drift == "owner": dry["owner_path"] = "/another/script.py"
    elif drift == "source": dry["source_sha256"] = {"source.py": "b" * 64}
    elif drift == "service": dry["service_started"] = True
    elif drift == "passed": dry["passed"] = False
    path.write_text(json.dumps(dry)); path.chmod(0o644 if drift == "writable" else 0o444)
    review = legacy.review_path(); review.parent.mkdir(parents=True)
    document = {"schema": owned.REVIEW_SCHEMA, "rid": owned.RID, "card": legacy.CARD,
                "candidate_commit": legacy.CANDIDATE_COMMIT, "parent_commit": legacy.PARENT_COMMIT,
                "verdict": "PASS", "approved": True, "source_sha256": owned.source_hashes(),
                "dry_run_receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "dry_run_source_sha256": owned.source_hashes()}
    review.write_text(json.dumps(document)); review.chmod(0o444)
    try:
        if drift is None: assert legacy.require_leaf_review() == review
        else:
            with pytest.raises(RuntimeError): legacy.require_leaf_review()
    finally:
        path.chmod(0o644); review.chmod(0o644)
