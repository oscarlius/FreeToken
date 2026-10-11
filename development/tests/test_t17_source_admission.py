import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("t17_source_admission_tests", Path(__file__).parents[1] / "t17_source_admission.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def report():
    return {"schema": "ft_t17_gpu_source_cpu/v1", "verdict": "PASS", "runtime_lifecycle_verified": False,
            "model_admitted": False, "admitted": False, "gpu_started": False, "requests_sent": False,
            "fixture_only": True, "real_gpu_lock_unchanged": True, "cpu_lifecycle_contract_verified": True}


def test_t20_source_profile_isolated_from_t17_and_rejects_old_schema():
    owned = m.for_run("t20")
    assert owned.CANDIDATE == "0aa23431e5b800797543bdecbf35a01045131d7d"
    assert owned.PARENT == "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
    assert owned.WORKTREE.as_posix() == "/data2/FreeToken/wt/e2base1-ordinary-rewind"
    assert (owned.WORKTREE / "python").as_posix() in owned.IMPORT_CODE
    assert "e2d14-ordinary-rewind" not in owned.IMPORT_CODE
    assert "t20_measurements,e2_runtime,t08_runner" in owned.IMPORT_CODE
    assert {"t20_measurements.py", "e2_runtime.py", "t08_runner.py", "d07_g3g4_prepare.py"} <= set(owned.T20_SOURCE_FILES)
    assert m.CANDIDATE == "a9dca443cd07e1f60d1533e0a678935a09d21636"
    assert m.CPU_SCHEMA == "ft_t17_gpu_source_cpu/v1"
    with pytest.raises(owned.AdmissionError, match="schema/verdict"):
        owned._cpu_flags(report())
    value = report(); value["schema"] = owned.CPU_SCHEMA
    owned._cpu_flags(value)
    value["model_admitted"] = True
    with pytest.raises(owned.AdmissionError, match="cannot substitute"):
        owned._cpu_flags(value)


def test_source_profile_rejects_unknown_run_kind():
    with pytest.raises(m.AdmissionError, match="unknown"):
        m.for_run("other")


@pytest.mark.parametrize("key", ["runtime_lifecycle_verified", "model_admitted", "admitted", "gpu_started", "requests_sent"])
def test_cpu_flags_reject_runtime_model_or_gpu_admission(key):
    value = report(); value[key] = True
    with pytest.raises(m.AdmissionError, match="cannot substitute model acceptance"):
        m._cpu_flags(value)


@pytest.mark.parametrize("name", ["../escape.json", "/tmp/escape.json"])
def test_inventory_rejects_path_escape(tmp_path, name):
    with pytest.raises(m.AdmissionError, match="unsafe evidence path"):
        m.verify_map(tmp_path, {name: "a" * 64})


def test_inventory_recomputes_readonly_bytes(tmp_path):
    path = tmp_path / "source.py"; path.write_text("new"); path.chmod(0o444)
    with pytest.raises(m.AdmissionError, match="SHA differs"):
        m.verify_map(tmp_path, {"source.py": hashlib.sha256(b"old").hexdigest()})


def test_actual_replay_receipt_contract_uses_real_suffix_and_flags(tmp_path):
    stage = tmp_path / "stage"; stage.mkdir(); stage.chmod(0o555)
    assert m.SCENARIOS == ("success", "request_error", "stop_error")
    assert "_replay.json" not in m.SCENARIOS
    assert "original_model_generation" in Path(m.HERE / "t17_v2_retained_replay.py").read_text()


def test_cpu_package_rejects_report_outside_its_stage(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "HERE", tmp_path / "stage" / "source_tools")
    with pytest.raises(m.AdmissionError, match="own startup CPU report"):
        m.check_cpu_package(tmp_path / "other_report.json")


def calls(*pids, recovered=False):
    result = [{"kind": "cpu_service", "identity": {"pid": pid, "start_ticks": pid + 100,
              "execution_id": f"{pid}:{pid + 100}"}} for pid in pids]
    result.extend({"kind": "cpu_stop", "pid": pid, "group_dead": True,
                   **({"recovered_after_stop_error": True} if recovered else {})} for pid in pids)
    return result


@pytest.mark.parametrize("scenario,pids", [("success", (11, 12, 13, 14)), ("request_error", (21,))])
def test_replay_stop_evidence_matches_all_born_children(scenario, pids):
    m._verify_stop_evidence(scenario, calls(*pids))


@pytest.mark.parametrize("mutation", ["wrong_pid", "duplicate_stop", "missing_stop", "live_group"])
def test_replay_stop_evidence_rejects_pid_mismatch_or_incomplete_cleanup(mutation):
    value = calls(11, 12, 13, 14)
    if mutation == "wrong_pid": value[-1]["pid"] = 99
    elif mutation == "duplicate_stop": value[-1]["pid"] = 13
    elif mutation == "missing_stop": value.pop()
    else: value[-1]["group_dead"] = False
    with pytest.raises(m.AdmissionError, match="stop"):
        m._verify_stop_evidence("success", value)


def test_stop_error_requires_failed_birth_and_explicit_recovery():
    value = calls(31, recovered=True)
    value.insert(1, {"kind": "stop_failed", "pid": 31})
    m._verify_stop_evidence("stop_error", value)
    value[-1]["recovered_after_stop_error"] = False
    with pytest.raises(m.AdmissionError, match="recovery"):
        m._verify_stop_evidence("stop_error", value)


@pytest.fixture
def external_review(monkeypatch, tmp_path):
    package = tmp_path / "package"; package.mkdir()
    monkeypatch.setattr(m, "HERE", package / "source_tools")
    checked = {"stage_report_sha256": "a" * 64, "candidate_commit": m.CANDIDATE,
               "parent_commit": m.PARENT, "source_execution_ready": False, "model_admitted": False,
               "runtime_lifecycle_verified": False}
    monkeypatch.setattr(m, "check_cpu_package", lambda _: checked.copy())
    directory = tmp_path / "independent"; directory.mkdir()
    path = directory / "review.json"
    value = {"schema": "ft_t17_gpu_source_admission_review/v1", "scope": "owned-gpu-test-startup-only",
             "verdict": "PASS", "stage_report_sha256": "a" * 64, "candidate_commit": m.CANDIDATE,
             "parent_commit": m.PARENT, "runtime_lifecycle_verified": False, "model_admitted": False,
             "admitted": False, "gpu_started": False, "requests_sent": False,
             "reviewer_identity": "/root/r_overlap_review"}
    def write(current):
        directory.chmod(0o755)
        if path.exists(): path.chmod(0o644)
        path.write_text(json.dumps(current)); path.chmod(0o444); directory.chmod(0o555)
        return m.sha(path)
    pin = write(value)
    try:
        yield path, value, pin, write
    finally:
        directory.chmod(0o755)
        if path.exists(): path.chmod(0o644)


def test_external_review_admits_source_only(external_review):
    path, value, pin, write = external_review
    result = m.verify(Path("cpu.json"), path, pin)
    assert result["source_execution_ready"] is True
    assert result["model_admitted"] is False
    assert result["runtime_lifecycle_verified"] is False


def test_t20_rejects_t17_review_even_with_current_candidate(external_review, monkeypatch):
    path, value, pin, write = external_review
    with monkeypatch.context() as source:
        source.setattr(m, "HERE", Path(__file__).parents[1])
        owned = m.for_run("t20")
    monkeypatch.setattr(owned, "HERE", m.HERE)
    monkeypatch.setattr(owned, "check_cpu_package", lambda _: {
        "stage_report_sha256": "a" * 64, "candidate_commit": owned.CANDIDATE,
        "parent_commit": owned.PARENT, "source_execution_ready": False,
        "model_admitted": False, "runtime_lifecycle_verified": False})
    value.update(candidate_commit=owned.CANDIDATE, parent_commit=owned.PARENT)
    pin = write(value)
    with pytest.raises(owned.AdmissionError, match="review binding differs"):
        owned.verify(Path("cpu.json"), path, pin)
    value["schema"] = owned.REVIEW_SCHEMA
    result = owned.verify(Path("cpu.json"), path, write(value))
    assert result["source_execution_ready"] is True
    assert result["model_admitted"] is False


def test_unreviewed_package_is_never_source_ready(monkeypatch):
    checked = {"source_execution_ready": False, "model_admitted": False, "runtime_lifecycle_verified": False}
    monkeypatch.setattr(m, "check_cpu_package", lambda _: checked.copy())
    assert m.verify(Path("cpu.json"))["source_execution_ready"] is False


@pytest.mark.parametrize("key,bad", [
    ("scope", "model-acceptance"), ("stage_report_sha256", "b" * 64),
    ("candidate_commit", "bad"), ("parent_commit", "bad"),
    ("runtime_lifecycle_verified", True), ("model_admitted", True), ("admitted", True),
    ("gpu_started", True), ("requests_sent", True), ("reviewer_identity", "/root/producer"),
])
def test_external_review_tampering_rejected(external_review, key, bad):
    path, value, pin, write = external_review
    value[key] = bad; pin = write(value)
    with pytest.raises(m.AdmissionError, match="review binding differs"):
        m.verify(Path("cpu.json"), path, pin)


def test_external_review_requires_caller_sha(external_review):
    path, value, pin, write = external_review
    with pytest.raises(m.AdmissionError, match="caller-pinned"):
        m.verify(Path("cpu.json"), path, None)


def test_external_review_requires_readonly_parent(external_review):
    path, value, pin, write = external_review
    path.parent.chmod(0o755)
    with pytest.raises(m.AdmissionError, match="sealed evidence directory"):
        m.verify(Path("cpu.json"), path, pin)


def test_external_review_replacement_rejected_by_raw_sha(external_review):
    path, value, pin, write = external_review
    value["extra"] = "replacement"; write(value)
    with pytest.raises(m.AdmissionError, match="review SHA differs"):
        m.verify(Path("cpu.json"), path, pin)
