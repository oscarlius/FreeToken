import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("t17_continuation_launch", HERE / "t17_continuation_launch.py")
launch = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(launch)


def test_preflight_uses_actual_reserved_round_and_runner_without_run(monkeypatch, tmp_path):
    monkeypatch.setattr(launch, "ROOT", tmp_path)
    stage, template = tmp_path / "stage", tmp_path / "batch.sh"; stage.mkdir(); template.write_text("#!/bin/bash\n")
    calls = []; rounds = iter((33, 33)); batches = iter((71, 71))
    protocol = SimpleNamespace(next_round=lambda _: next(rounds), HELPER_SHA="x", verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: next(batches)))
    monkeypatch.setattr(launch, "read_stage", lambda _: ({"files": {"t17_continuation_runner.py": "x", "batchNN_T17.sh": "template"}}, "report") )
    monkeypatch.setattr(launch, "read_review", lambda *_: {"verdict": "PASS", "batch_template_sha256": "template"})
    monkeypatch.setattr(launch, "load_protocol", lambda: protocol)
    monkeypatch.setattr(launch, "batch_template", lambda: template)
    monkeypatch.setattr(launch, "checked", lambda *_a, **_k: None)
    monkeypatch.setattr(launch, "ROUNDS", tmp_path / "rounds"); launch.ROUNDS.mkdir()
    monkeypatch.setenv("FT_T17_INPUTS", "inputs.json"); monkeypatch.setenv("FT_T17_CLOSURE_BINDING", "closure.json")
    monkeypatch.setattr(launch.subprocess, "run", lambda argv, **kw: calls.append((argv, kw)))
    result = launch.preflight(stage, tmp_path / "review.json")
    assert result[6:8] == ("E2-R033", 71)
    assert calls[0][0][3:7] == ["--rid", "E2-R033", "--batch", "71"] and "--run" not in calls[0][0]
    assert calls[0][0][-1] == "--resource-preflight"


def test_preflight_rejects_non_reserved_round(monkeypatch, tmp_path):
    protocol = SimpleNamespace(next_round=lambda _: 35, HELPER_SHA="x", verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: 1))
    monkeypatch.setattr(launch, "read_stage", lambda _: ({"files": {"batchNN_T17.sh": "x"}}, "report")); monkeypatch.setattr(launch, "read_review", lambda *_: {"batch_template_sha256": "x"})
    monkeypatch.setattr(launch, "load_protocol", lambda: protocol)
    with pytest.raises(ValueError, match="reserved round"):
        launch.preflight(tmp_path, tmp_path / "review")


def test_preflight_rejects_existing_reservation_before_runner(monkeypatch, tmp_path):
    stage, template, root = tmp_path / "stage", tmp_path / "batch.sh", tmp_path / "root"
    stage.mkdir(); root.mkdir(); template.write_text("#!/bin/bash\n")
    receipt = root / "runs/dev_D16/launch_E2-R033.json"; receipt.parent.mkdir(parents=True); receipt.write_text("reserved")
    protocol = SimpleNamespace(next_round=lambda _: 33, HELPER_SHA="x", verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: 7))
    monkeypatch.setattr(launch, "read_stage", lambda _: ({"files": {"batchNN_T17.sh": "x"}}, "report"))
    monkeypatch.setattr(launch, "read_review", lambda *_: {"batch_template_sha256": "x"}); monkeypatch.setattr(launch, "load_protocol", lambda: protocol)
    monkeypatch.setattr(launch, "batch_template", lambda: template); monkeypatch.setattr(launch, "ROOT", root)
    monkeypatch.setattr(launch, "ROUNDS", tmp_path / "rounds"); launch.ROUNDS.mkdir(); monkeypatch.setattr(launch.subprocess, "run", lambda *_a, **_k: pytest.fail("runner started"))
    with pytest.raises(FileExistsError, match="receipt"):
        launch.preflight(stage, tmp_path / "review.json")


def test_preflight_rejects_environment_template_not_bound_to_stage(monkeypatch, tmp_path):
    stage, template = tmp_path / "stage", tmp_path / "other-template.sh"; stage.mkdir(); template.write_text("#!/bin/bash\n")
    protocol = SimpleNamespace(next_round=lambda _: 33, HELPER_SHA="x", verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: 7))
    monkeypatch.setattr(launch, "read_stage", lambda _: ({"files": {"batchNN_T17.sh": "approved"}}, "report"))
    monkeypatch.setattr(launch, "read_review", lambda *_: {"batch_template_sha256": "approved"}); monkeypatch.setattr(launch, "load_protocol", lambda: protocol)
    monkeypatch.setattr(launch, "batch_template", lambda: template); monkeypatch.setattr(launch, "ROUNDS", tmp_path / "rounds"); launch.ROUNDS.mkdir()
    monkeypatch.setattr(launch, "ROOT", tmp_path); monkeypatch.setattr(launch, "checked", lambda path, digest, **_: (_ for _ in ()).throw(ValueError("stage evidence SHA differs")) if path == template else None)
    with pytest.raises(ValueError, match="SHA differs"):
        launch.preflight(stage, tmp_path / "review.json")


def test_launch_reserves_before_atomic_start_and_passes_frozen_template(monkeypatch, tmp_path):
    template = tmp_path / "template.sh"; template.write_text("#!/bin/bash\n")
    review = tmp_path / "review.json"; review.write_text("{}")
    execution = tmp_path / "frozen"; execution.mkdir(); (execution / "batch_template.sh").write_text("#!/bin/bash\n")
    protocol = SimpleNamespace(reserve_process=lambda helper, batch, rid, argv, receipt, reserved: {
        "started_after_reserved": True, "argv": argv, "reserved": reserved})
    preflight = ({"files": {}}, "stage-sha", {}, protocol, object(), ["python"], "E2-R033", 72, template)
    monkeypatch.setattr(launch, "preflight", lambda *_, **__: preflight); monkeypatch.setattr(launch, "freeze", lambda *_: execution)
    monkeypatch.setattr(launch, "ROOT", tmp_path); monkeypatch.setenv("FT_T17_INPUTS", "i"); monkeypatch.setenv("FT_T17_CLOSURE_BINDING", "c")
    result = launch.launch(tmp_path / "stage", review)
    assert result["started_after_reserved"] and result["argv"][-2:] == [str(execution / "batch_template.sh"), "E2-R033"]
    assert "FT_T17_STAGE=" + str(execution) in result["argv"]
    assert result["reserved"]["stage_report_sha256"] == "stage-sha"


def _sealed_parent(rounds):
    parent = rounds / "E2-R034"; history = parent / "round_history"
    history.mkdir(parents=True)
    raw = json.dumps({"schema": "ft_round/v2", "verdict": "failed_harness"}, indent=2).encode() + b"\n"
    (parent / "round.json").write_bytes(raw)
    version = history / "round.v001.json"; version.write_bytes(raw)
    (history / "SHA256SUMS").write_bytes((hashlib.sha256(raw).hexdigest() + "  round.v001.json\n").encode("ascii"))
    batch = parent / "batch.sh"; batch.write_bytes(b"#!/usr/bin/env bash\n")
    (parent / "MANIFEST.sha256").write_bytes((hashlib.sha256(batch.read_bytes()).hexdigest() + "  ./batch.sh\n").encode("ascii"))
    return parent


def test_allocated_r034a_requires_sealed_parent_and_keeps_numeric_max_at_34(monkeypatch, tmp_path):
    stage, template, root, rounds = tmp_path / "stage", tmp_path / "batch.sh", tmp_path / "root", tmp_path / "rounds"
    stage.mkdir(); root.mkdir(); rounds.mkdir(); template.write_text("#!/bin/bash\n")
    parent = _sealed_parent(rounds)
    numeric = iter((35, 35)); batches = iter((63, 63)); calls = []
    protocol = SimpleNamespace(next_round=lambda _: next(numeric), HELPER_SHA="x",
                               verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: next(batches)))
    monkeypatch.setattr(launch, "read_stage", lambda _: ({"files": {"t17_continuation_runner.py": "x", "batchNN_T17.sh": "template"}}, "report"))
    monkeypatch.setattr(launch, "read_review", lambda *_: {"verdict": "PASS", "batch_template_sha256": "template"})
    monkeypatch.setattr(launch, "load_protocol", lambda: protocol); monkeypatch.setattr(launch, "batch_template", lambda: template)
    monkeypatch.setattr(launch, "checked", lambda *_a, **_k: None); monkeypatch.setattr(launch, "ROOT", root); monkeypatch.setattr(launch, "ROUNDS", rounds)
    monkeypatch.setenv("FT_T17_INPUTS", "inputs.json"); monkeypatch.setenv("FT_T17_CLOSURE_BINDING", "closure.json")
    monkeypatch.setattr(launch.subprocess, "run", lambda argv, **kw: calls.append((argv, kw)))
    result = launch.preflight(stage, tmp_path / "review.json", rid="E2-R034a")
    assert result[6:8] == ("E2-R034a", 63)
    assert calls[0][0][-1] == "check" and calls[0][0][-2] == str(parent)
    assert calls[1][0][3:7] == ["--rid", "E2-R034a", "--batch", "63"]
    assert not (rounds / "E2-R035").exists()


def test_supplement_refuses_unsealed_or_other_rid(monkeypatch, tmp_path):
    rounds = tmp_path / "rounds"; rounds.mkdir(); parent = _sealed_parent(rounds)
    document = json.loads((parent / "round.json").read_text()); document["verdict"] = "not_met"; (parent / "round.json").write_text(json.dumps(document))
    monkeypatch.setattr(launch, "ROUNDS", rounds)
    with pytest.raises(ValueError, match="failed_harness"):
        launch.sealed_failed_harness_parent()
    protocol = SimpleNamespace(next_round=lambda _: 35); atomic = SimpleNamespace(next_batch=lambda _: 63)
    with pytest.raises(ValueError, match="only allocated"):
        launch.allocate(protocol, atomic, "E2-R035")


def test_supplement_requires_batch_63_before_parent_check(monkeypatch, tmp_path):
    rounds = tmp_path / "rounds"; rounds.mkdir(); _sealed_parent(rounds)
    monkeypatch.setattr(launch, "ROUNDS", rounds)
    monkeypatch.setattr(launch.subprocess, "run", lambda *_a, **_k: pytest.fail("parent check must not run"))
    protocol = SimpleNamespace(next_round=lambda _: 35); atomic = SimpleNamespace(next_batch=lambda _: 62)
    with pytest.raises(ValueError, match="batch 63"):
        launch.allocate(protocol, atomic, "E2-R034a")
