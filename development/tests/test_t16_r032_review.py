import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


PATH = Path(__file__).parents[1] / "t16_r032_review.py"
SPEC = importlib.util.spec_from_file_location("r032_review", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_r032_declares_the_exact_eight_arm_matrix():
    assert MODULE.ARMS == (
        "PARENT_b60", "NEW_b60", "PARENT_P_b60", "NEW_P_b60",
        "CHUNK_PARENT_b60", "CHUNK_NEW_b60", "CHUNK_PARENT_P_b60", "CHUNK_NEW_P_b60",
    )
    assert MODULE.LAYER_ARMS == MODULE.ARMS[:4]
    assert MODULE.CHUNK_ARMS == MODULE.ARMS[4:]


def test_cases_are_mode_specific_and_keep_128_token_contract():
    assert MODULE.cases_for_mode("layer_major") == [("det", "", 32052, 128)]
    assert MODULE.cases_for_mode("non_layer_major") == [
        ("short", "", 2000, 128), ("chunked", "", 32052, 128)
    ]


@pytest.mark.parametrize("arm,mode", [
    ("PARENT_b60", "layer_major"), ("NEW_P_b60", "layer_major"),
    ("CHUNK_PARENT_b60", "non_layer_major"), ("CHUNK_NEW_P_b60", "non_layer_major"),
])
def test_arm_classification_is_exact(arm, mode):
    assert MODULE.mode_for_arm(arm) == mode


def test_unknown_arm_and_mode_fail_closed():
    with pytest.raises(ValueError):
        MODULE.mode_for_arm("PARENT_b59")
    with pytest.raises(ValueError):
        MODULE.cases_for_mode("future_mode")


def test_review_identity_is_pinned_to_actual_r032_launch():
    assert MODULE.RID == "E2-R032-gate-D14"
    assert MODULE.BATCH == 60
    assert MODULE.PARENT == "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
    assert MODULE.CANDIDATE == "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
    assert MODULE.CPU_STAGE_SHA == "458553a9db361c00ff4f1056604fc6c8807c086f27b66a1b363122c1b542736c"


def test_d18_archives_require_the_independent_binding_and_byte_hashes(tmp_path):
    probe = b"probe"
    probe_sha = hashlib.sha256(probe).hexdigest()
    probe_md5 = hashlib.md5(probe).hexdigest()
    class Schedule:
        PROBE_SHA = probe_sha
        PROBE_MD5 = probe_md5
        D18 = tmp_path / "frozen_receipt.json"
        D18_LOG = tmp_path / "frozen_log.txt"
        D18_TEST = tmp_path / "frozen_test.py"
    Schedule.D18_LOG.write_bytes(b"log")
    Schedule.D18_TEST.write_bytes(b"CPU tested source")
    test_sha = MODULE.sha(Schedule.D18_TEST)
    (tmp_path / "d18_independent_cpu_receipt.log").write_bytes(b"log")
    (tmp_path / "d18_probe_ft_cold32k.py").write_bytes(probe)
    receipt = {"schema": "ft_d18_independent_cpu/v1", "returncode": 0, "gpu_started": False,
               "requests_sent": False, "log_sha256": hashlib.sha256(b"log").hexdigest(),
               "source_files": {"scripts/probe_ft_cold32k.py": probe_sha,
                                "../_shared/benchmark_client.py": "b" * 64,
                                "tests/test_d18_client_params.py": test_sha}}
    (tmp_path / "d18_independent_cpu_receipt.json").write_text(json.dumps(receipt))
    Schedule.D18.write_text(json.dumps(receipt))
    expected = {"receipt_sha256": hashlib.sha256((tmp_path / "d18_independent_cpu_receipt.json").read_bytes()).hexdigest(),
                "log_sha256": receipt["log_sha256"], "probe_sha256": probe_sha, "probe_md5": probe_md5,
                "benchmark_sha256": "b" * 64, "test_sha256": test_sha}
    (tmp_path / "d18_binding.json").write_text(json.dumps(expected))
    assert MODULE.verify_d18_archives(tmp_path, Schedule()) == expected
    archive = tmp_path / "d18_independent_cpu_receipt.json"
    original = archive.read_bytes(); archive.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="frozen CPU-tested"):
        MODULE.verify_d18_archives(tmp_path, Schedule())
    archive.write_bytes(original)
    (tmp_path / "d18_probe_ft_cold32k.py").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="D18 frozen probe"):
        MODULE.verify_d18_archives(tmp_path, Schedule())


def test_stage_rejects_a_writable_tampered_stage(monkeypatch, tmp_path):
    files = {f"x{index}": "y" for index in range(29)}
    report = {"schema": "ft_t16_d14_schedule_stage/v1", "verdict": "PASS", "gpu_started": False,
              "requests_sent": False, "passed": 75, "files": files, "steps": {}}
    receipt = {"source_stage": str(tmp_path), "cpu_stage_sha256": MODULE.CPU_STAGE_SHA,
               "source_files": files}
    monkeypatch.setattr(MODULE, "guarded", lambda path: tmp_path)
    monkeypatch.setattr(MODULE, "load", lambda path: report)
    monkeypatch.setattr(MODULE, "sha", lambda path: MODULE.CPU_STAGE_SHA)
    with pytest.raises(ValueError, match="writable frozen"):
        MODULE._verify_stage(receipt, tmp_path)


def test_status_birth_is_optional_but_wrong_value_is_explicitly_rejected():
    status = {"rid": MODULE.RID, "batch": MODULE.BATCH, "batch_pid": MODULE.BATCH_PID,
              "candidate_case": "D14-schedule", "state": "complete_measurements_pending_review"}
    MODULE.validate_status(status)
    status["batch_start_ticks"] = MODULE.BATCH_START_TICKS + 1
    with pytest.raises(ValueError, match="status birth"):
        MODULE.validate_status(status)
    status.pop("batch_start_ticks"); status["candidate_case"] = "D14"
    with pytest.raises(ValueError, match="status identity"):
        MODULE.validate_status(status)
