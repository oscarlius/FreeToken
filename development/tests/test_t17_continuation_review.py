import importlib.util
import json
from pathlib import Path
import shutil

import pytest

PATH = Path(__file__).parents[1] / "t17_continuation_review.py"
SPEC = importlib.util.spec_from_file_location("t17_continuation_review", PATH)
review = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(review)


def row(verdict): return {"case":"c", "verdict":verdict}


def test_not_met_and_failed_harness_can_stop_before_28_cases():
    assert review.classify([row("not_met")], {"state":"failed"}) == "not_met"
    assert review.classify([row("failed_harness")], {"state":"failed"}) == "failed_harness"


def test_kept_requires_complete_measurements_and_all_cases():
    cases = [row("measurements_pass_pending_independent_review") for _ in range(28)]
    assert review.classify(cases, {"state":"complete_measurements_pending_independent_review"}) == "kept_pending_independent_review"
    with pytest.raises(ValueError, match="28"):
        review.classify(cases[:-1], {"state":"complete_measurements_pending_independent_review"})


def test_launch_source_tamper_and_symlink_are_rejected(tmp_path):
    directory = tmp_path / "E2-R033"; directory.mkdir(); source = directory / "source_tools"; source.mkdir()
    runner = source / "t17_continuation_runner.py"; runner.write_text("approved")
    receipt = tmp_path / "launch.json"; receipt.write_text('{"rid":"E2-R033","batch":1,"candidate_commit":"e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7","source_files":{"t17_continuation_runner.py":"' + review.sha(runner) + '"}}')
    review.verify_launch(directory, receipt)
    runner.write_text("tampered")
    with pytest.raises(ValueError, match="SHA"):
        review.verify_launch(directory, receipt)
    class FakePath:
        def is_symlink(self): return True
    class FakeDirectory:
        def is_symlink(self): return False
        def is_dir(self): return True
        def rglob(self, _): return [FakePath()]
    with pytest.raises(ValueError, match="symlink"):
        review.no_symlinks(FakeDirectory())


def test_audit_accepts_ordered_early_not_met_prefix(monkeypatch, tmp_path):
    directory = tmp_path / "E2-R033"; directory.mkdir(); cases = directory / "cases"; cases.mkdir()
    case = {"name":"first", "length":2, "tail":1, "query":[1,2,3], "input_ids_sha256":"x", "expected_ngram":[1,2]}
    (directory / "real_inputs.json").write_text(json.dumps({"candidate_commit":review.CANDIDATE,"cases":[case,{**case,"name":"later"}]}))
    (directory / "result.json").write_text(json.dumps({"verdict":"not_met","cases":{"first":{}}}))
    (cases / "first.json").write_text(json.dumps({"result":{"verdict":"not_met"}}))
    receipt = tmp_path / "launch.json"; receipt.write_text("{}")
    status = tmp_path / "status.json"; status.write_text(json.dumps({"rid":"E2-R033","batch":9,"state":"failed"}))
    monkeypatch.setattr(review, "no_symlinks", lambda *_: None)
    monkeypatch.setattr(review, "verify_launch", lambda *_: {"batch":9})
    monkeypatch.setattr(review, "verify_round_bindings", lambda *_: None)
    monkeypatch.setattr(review, "audit_case", lambda *_: {"case":"first","verdict":"not_met"})
    output = review.audit(directory, receipt, status, readers=object())
    assert output["verdict"] == "not_met" and [item["case"] for item in output["cases"]] == ["first"]


def test_reference_identity_binds_saved_api_identity_to_actual_arm_files(tmp_path):
    arm = tmp_path / "reference"; arm.mkdir()
    (arm / "serve_args.txt").write_text(json.dumps({"_unique_suffix":"'.pid=123'"}))
    (arm / "ENV.txt").write_text(review.CANDIDATE + "\n")
    (arm / "serve.log").write_text("stopped\n")
    declared = {"pid":123,"start_ticks":9,"execution_id":"123:9"}
    assert review.identity(arm, declared) == declared
    with pytest.raises(ValueError, match="PID"):
        review.identity(arm, {**declared,"pid":124,"execution_id":"124:9"})


def test_load_readers_imports_archived_real_equiv_sources_without_gpu(tmp_path):
    directory = tmp_path / "E2-R033"; source = directory / "source_tools"; suite = source / "equiv_suite"
    suite.mkdir(parents=True)
    development = PATH.parent
    for item in (development / "e2d16-tools/scripts/equiv_suite").glob("*.py"):
        shutil.copyfile(item, suite / item.name)
    shutil.copyfile(development / "t17_d14_artifacts.py", source / "t17_d14_artifacts.py")
    shutil.copyfile(development / "t17_operator_observe.py", source / "t17_operator_observe.py")
    readers = review.load_readers(directory)
    assert readers.raw.__name__.endswith(".raw") and readers.gate.ROLES == ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")


def test_audit_records_pre_result_failed_harness(monkeypatch, tmp_path):
    directory = tmp_path / "E2-R033"; directory.mkdir()
    (directory / "real_inputs.json").write_text(json.dumps({"candidate_commit":review.CANDIDATE,"cases":[]}))
    (directory / "failed_harness.json").write_text(json.dumps({"error":"owned service failed"}))
    receipt = tmp_path / "launch.json"; receipt.write_text("{}")
    status = tmp_path / "status.json"; status.write_text(json.dumps({"rid":"E2-R033","batch":9,"state":"failed"}))
    monkeypatch.setattr(review, "no_symlinks", lambda *_: None); monkeypatch.setattr(review, "verify_launch", lambda *_: {"batch":9})
    monkeypatch.setattr(review, "verify_round_bindings", lambda *_: None)
    output = review.audit(directory, receipt, status, readers=object())
    assert output["verdict"] == "failed_harness" and output["cases"] == []
