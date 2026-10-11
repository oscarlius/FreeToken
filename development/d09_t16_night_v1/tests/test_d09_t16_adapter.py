import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


PACKAGE = Path(__file__).parents[1]


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, PACKAGE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_identity_and_only_default_off_delta():
    module = load("d09_t16_full_runner.py")
    assert module.ASSIGNED_RID == "E2-D09-T16-night-20261009"
    assert module.CASES["D09"]["parent_commit"] == "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
    assert module.CASES["D09"]["new_commit"] == "c17b69a46cd512fbf3d127d3879bce92caae457b"
    module.CandidateRunner.assert_default_off_args({"a": "1"}, {"a": "1", "message_boundary_ckpt": "False"})
    with pytest.raises(ValueError, match="default-off"):
        module.CandidateRunner.assert_default_off_args({"a": "1"}, {"a": "1", "message_boundary_ckpt": "True"})
    with pytest.raises(ValueError, match="outside"):
        module.CandidateRunner.assert_default_off_args({"a": "1"}, {"a": "2", "message_boundary_ckpt": "False"})


def test_prepare_reports_actual_runner_and_scope_budget(capsys):
    module = load("d09_owned_launch.py")
    assert module.main([]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["gates"]["D09"][0] == "E2-D09-T16-night-20261009"
    assert module.D09_QUEUE_PREDECESSORS == ("E2-R047", "Strata", "E2-R052a", "E2-R044")


def test_file_dry_protocol_mock_writes_eight_arms_without_service(monkeypatch, tmp_path):
    module = load("d09_t16_full_runner.py")
    monkeypatch.setattr(module, "ROOT", tmp_path / "source")
    monkeypatch.setattr(module, "ROUNDS", tmp_path)
    monkeypatch.setattr(module, "WRAPPERS", tmp_path)
    monkeypatch.setitem(module.base, "ROOT", tmp_path / "source")
    monkeypatch.setitem(module.base, "ROUNDS", tmp_path)
    monkeypatch.setitem(module.base, "TOOL_MD5", {})
    monkeypatch.setitem(module.base, "has_d02_prefill_tail", lambda *_: True)
    monkeypatch.setitem(module.base, "command", lambda argv, **_: module.CASES["D09"]["parent_commit"] if argv[0] == "git" else "CPU metadata")
    monkeypatch.setattr(module.CandidateRunner, "gate", lambda *_: "source fixture")
    monkeypatch.setattr(module, "require_native_provenance", lambda: None)
    monkeypatch.setattr(module, "validate_extensions", lambda *_: None)
    monkeypatch.setattr(module.CandidateRunner, "compiled_extensions", lambda *_: {"cpu": {"sha256": "fixture"}})
    monkeypatch.setattr(module.base["subprocess"], "Popen", lambda *_a, **_k: pytest.fail("dry run launched a service"))
    wrapper = tmp_path / "wrapper.sh"; wrapper.write_text("CPU wrapper")
    options = SimpleNamespace(case="D09", rid=module.ASSIGNED_RID, batch=1,
                              candidate_commit=module.CASES["D09"]["new_commit"], run=True,
                              gate=None, file_dry_run=True, dry_run_wrapper=str(wrapper))
    runner = module.CandidateRunner(options)
    runner.directory = tmp_path / "dry" / "round"; runner.directory.parent.mkdir()
    runner.status = runner.directory / "status.json"
    runner.execute()
    complete = json.loads((runner.directory / "file_dry_run_complete.json").read_text())
    assert len(complete["arms"]) == 8
    assert all(complete[key] is False for key in ("service_started", "requests_sent", "gpu_lock_taken"))
