import importlib.util
import json
from pathlib import Path
import os
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location("t17_launch_v3_tests", Path(__file__).parents[1] / "t17_continuation_launch_v3.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def template_path():
    flat = Path(m.__file__).parent / "batchNN_T17_v3.sh"
    return flat if flat.is_file() else Path(__file__).parents[2] / "plan/01_测试与调研/batches/batchNN_T17_v3.sh"


def test_build_command_binds_actual_v2_run_arguments(tmp_path):
    command = m.build_command(tmp_path / "batch.sh", stage=tmp_path / "stage", root=tmp_path / "stage/source_tools",
                              rid="E2-R035", batch=77, inputs=tmp_path / "inputs.json", closure=tmp_path / "closure.json",
                              review=tmp_path / "review.json", review_sha256="a" * 64,
                              receipt=tmp_path / "launch_E2-R035.json", rounds=tmp_path / "rounds")
    assert command[-3:] == ["bash", str(tmp_path / "batch.sh"), "E2-R035"]
    joined = "\0".join(command)
    for expected in ("FT_T17_BATCH=77", "FT_T17_SOURCE_REVIEW_SHA256=" + "a" * 64,
                     "FT_T17_BATCH_TEMPLATE=" + str(tmp_path / "batch.sh"),
                     "FT_T17_PREFLIGHT_ARTIFACT=" + str(tmp_path / "launch_E2-R035.preflight.json"),
                     "FT_T17_SOURCE_ROOT=" + str(tmp_path / "stage/source_tools")):
        assert expected in joined


def test_remaining_command_carries_same_pinned_review_as_dry_run(monkeypatch, tmp_path):
    review = tmp_path / "retained_review.json"
    review.write_text('{"reuse_permitted":false}')
    monkeypatch.setattr(m, "frozen", lambda path: None)
    digest = m.sha(review)
    args = m._case_args("remaining", review, digest)
    assert args == ["--cases", "remaining", "--resume-review", str(review), "--resume-review-sha256", digest]
    command = m.build_command(tmp_path / "batch.sh", stage=tmp_path / "stage", root=tmp_path / "source",
                              rid="E2-R038", batch=67, inputs=tmp_path / "inputs", closure=tmp_path / "closure",
                              review=tmp_path / "source_review", review_sha256="a" * 64,
                              receipt=tmp_path / "launch.json", rounds=tmp_path / "rounds",
                              cases="remaining", resume_review=review, resume_review_sha256=digest)
    assert "FT_T17_CASES=remaining" in command
    assert "FT_T17_RESUME_REVIEW=" + str(review) in command
    assert "FT_T17_RESUME_REVIEW_SHA256=" + digest in command
    review.write_text('{}')
    with pytest.raises(m.LaunchError, match="SHA differs"):
        m._case_args("remaining", review, digest)


@pytest.mark.parametrize("cases,review,digest", [("remaining", None, None), ("all", "/review", "a" * 64), ("bad", None, None)])
def test_case_mode_rejects_missing_or_ignored_resume_proof(cases, review, digest):
    with pytest.raises(m.LaunchError, match="explicit pinned"):
        m._case_args(cases, review, digest)


@pytest.mark.parametrize("rid", ["E2-R034a", "E2-R040", "E2-R035-gate-T17", "bad"])
def test_preflight_rejects_unassigned_rid_before_any_stage_io(rid, tmp_path):
    with pytest.raises(m.LaunchError, match="M-assigned"):
        m.preflight(tmp_path / "stage", tmp_path / "source-review.json", "a" * 64,
                    launcher_review=tmp_path / "launcher-review.json", launcher_review_sha256="b" * 64,
                    rid=rid, inputs=tmp_path / "inputs", closure=tmp_path / "closure", template=tmp_path / "batch")


def test_source_startup_review_cannot_be_promoted_to_model_admission(monkeypatch, tmp_path):
    root = tmp_path / "stage" / "source_tools"; root.mkdir(parents=True)
    (root / "cpu_validation.json").write_text("legacy")
    report = tmp_path / "stage" / "startup_cpu_report.json"; report.write_text("startup")
    class Admission:
        def verify(self, *args):
            return {"source_execution_ready": True, "runtime_lifecycle_verified": False,
                    "model_admitted": True, "candidate_commit": m.CANDIDATE, "parent_commit": m.PARENT}
    monkeypatch.setattr(m, "load_admission", lambda stage: (Admission(), report, {"files": {"t17_source_admission.py": "x"}}))
    monkeypatch.setattr(m, "source_root", lambda stage: root)
    with pytest.raises(m.LaunchError, match="cannot admit runtime/model"):
        m.verify_source_startup(tmp_path / "stage", tmp_path / "review", "a" * 64)


class Protocol:
    def __init__(self): self.published = []
    def reserve_process(self, atomic, batch, rid, command, receipt, reserved):
        receipt.write_text("reserved")
        return {**reserved, "batch_pid": 4242, "batch_pgid": 4242}
    def publish_receipt(self, receipt, identity, value):
        self.published.append((receipt, identity, value))
    def next_round(self, rounds): return 35
    def stop_owned_process(self, process): raise AssertionError("not expected")
    def write_exclusive(self, path, value): path.write_text("cleanup")


class Atomic:
    def next_batch(self, rounds): return 77


def result(tmp_path):
    return {"rid": "E2-R035", "batch": 77, "rounds": str(tmp_path / "rounds"),
            "receipt": str(tmp_path / "receipts" / "launch_E2-R035.json"), "command": ["env", "bash", "batch", "E2-R035"],
            "batch_log": str(tmp_path / "batch77.log"), "expected_round_number": 35,
            "stage": "/stage", "source_root": "/stage/source_tools", "startup": {"startup_report_sha256": "a" * 64,
            "independent_review_sha256": "b" * 64, "legacy_cpu_validation_sha256": "c" * 64, "files": {"runner.py": "d" * 64}},
            "launcher": {"launcher_review_sha256": "e" * 64, "launcher_sha256": "f" * 64, "batch_template_sha256": "0" * 64},
            "runner_sha256": "1" * 64, "runner_files": {"t17_continuation_runner.py": "d" * 64},
            "inputs_sha256": "2" * 64, "closure_sha256": "3" * 64}


def test_launch_uses_owned_protocol_and_publishes_birth_identity(monkeypatch, tmp_path):
    value = result(tmp_path); Path(value["rounds"]).mkdir(); Path(value["receipt"]).parent.mkdir()
    lock = tmp_path / "gpu.lock"; monkeypatch.setattr(m, "GPU_LOCK", lock)
    monkeypatch.setattr(m, "_identity", lambda process: {"batch_pid": 4242, "batch_pgid": 4242,
                                                           "batch_start_ticks": 81, "batch_execution_id": "4242:81"})
    protocol = Protocol()
    receipt = m.launch(value, protocol=protocol, atomic=Atomic())
    assert receipt["batch_execution_id"] == "4242:81"
    assert protocol.published[0][2]["batch_start_ticks"] == 81
    assert protocol.published[0][2]["runner_source_inventory"] == {"t17_continuation_runner.py": "d" * 64}
    assert protocol.published[0][2]["source_files"] == {"t17_continuation_runner.py": "d" * 64}
    assert protocol.published[0][2]["stage_report_sha256"] == "c" * 64


@pytest.mark.parametrize("state", ["lock", "round", "receipt"])
def test_launch_rejects_changed_identity_or_foreign_lock(monkeypatch, tmp_path, state):
    value = result(tmp_path); rounds = Path(value["rounds"]); rounds.mkdir(); Path(value["receipt"]).parent.mkdir()
    lock = tmp_path / "gpu.lock"; monkeypatch.setattr(m, "GPU_LOCK", lock)
    if state == "lock": lock.write_text("foreign")
    elif state == "round": (rounds / value["rid"]).mkdir()
    else: Path(value["receipt"]).write_text("already reserved")
    with pytest.raises(m.LaunchError, match="identity or GPU"):
        m.launch(value, protocol=Protocol(), atomic=Atomic())


def test_launch_rechecks_round_and_batch_ledger(monkeypatch, tmp_path):
    value = result(tmp_path); Path(value["rounds"]).mkdir(); Path(value["receipt"]).parent.mkdir()
    monkeypatch.setattr(m, "GPU_LOCK", tmp_path / "gpu.lock")
    protocol = Protocol(); protocol.next_round = lambda rounds: 36
    with pytest.raises(m.LaunchError, match="identity or GPU"):
        m.launch(value, protocol=protocol, atomic=Atomic())


def test_launch_rechecks_atomic_helper_batch_log_under_rounds(monkeypatch, tmp_path):
    value = result(tmp_path); rounds = Path(value["rounds"]); rounds.mkdir(); Path(value["receipt"]).parent.mkdir()
    value["batch_log"] = str(rounds / "batch77.log")
    Path(value["batch_log"]).write_text("already allocated")
    monkeypatch.setattr(m, "GPU_LOCK", tmp_path / "gpu.lock")
    with pytest.raises(m.LaunchError, match="identity or GPU"):
        m.launch(value, protocol=Protocol(), atomic=Atomic())


def test_launch_requires_source_inventory_that_the_independent_auditor_can_read(monkeypatch, tmp_path):
    value = result(tmp_path); value["runner_files"] = {}
    Path(value["rounds"]).mkdir(); Path(value["receipt"]).parent.mkdir()
    monkeypatch.setattr(m, "GPU_LOCK", tmp_path / "gpu.lock")
    with pytest.raises(m.LaunchError, match="legacy runner source inventory"):
        m.launch(value, protocol=Protocol(), atomic=Atomic())


def test_identity_publish_failure_stops_the_same_owned_pid(monkeypatch, tmp_path):
    value = result(tmp_path); Path(value["rounds"]).mkdir(); Path(value["receipt"]).parent.mkdir()
    monkeypatch.setattr(m, "GPU_LOCK", tmp_path / "gpu.lock")
    monkeypatch.setattr(m, "_identity", lambda process: {"batch_pid": 4242, "batch_pgid": 4242,
                                                           "batch_start_ticks": 81, "batch_execution_id": "4242:81"})
    protocol = Protocol(); stopped = []
    def fail(*args): raise RuntimeError("receipt replace failed")
    protocol.publish_receipt = fail
    protocol.stop_owned_process = lambda process: stopped.append(process.pid)
    with pytest.raises(m.LaunchError, match="identity receipt"):
        m.launch(value, protocol=protocol, atomic=Atomic())
    assert stopped == [4242]
    assert Path(value["receipt"] + ".identity_cleanup.json").is_file()


def test_identity_probe_failure_also_stops_the_same_owned_pid(monkeypatch, tmp_path):
    value = result(tmp_path); Path(value["rounds"]).mkdir(); Path(value["receipt"]).parent.mkdir()
    monkeypatch.setattr(m, "GPU_LOCK", tmp_path / "gpu.lock")
    monkeypatch.setattr(m, "_identity", lambda process: (_ for _ in ()).throw(OSError("proc disappeared")))
    protocol = Protocol(); stopped = []
    protocol.stop_owned_process = lambda process: stopped.append(process.pid)
    with pytest.raises(m.LaunchError, match="identity receipt"):
        m.launch(value, protocol=protocol, atomic=Atomic())
    assert stopped == [4242]


def test_preflight_result_contract_is_json_native():
    value = result(Path("/tmp"))
    json.dumps(value, sort_keys=True)


def test_v3_batch_template_has_no_legacy_runner_or_batch63_binding():
    text = template_path().read_text()
    assert "t17_continuation_runner_v2.py" in text
    assert '--run-kind t17 --cases "$cases" "${resume_args[@]}" --envelope-cases sample4' in text
    assert 'cases="${FT_T17_CASES:-all}"' in text
    assert '[[ "$2" != "--run" ]]' in text
    assert "batch63" not in text
    assert "t17_continuation_runner.py\"" not in text


@pytest.mark.skipif(os.name == "nt", reason="the Windows-hosted bash cannot execute a UTF-8 shell fixture reliably")
def test_v3_batch_template_accepts_the_atomic_helper_appended_run_argument(tmp_path):
    template = tmp_path / "batchNN_T17_v3.sh"
    # Keep the actual wrapper intact through its argument/environment gates, but
    # replace only its host-specific exec boundary with a deterministic marker.
    template.write_text(template_path().read_text().split("exec /data2/FreeToken/venv/bin/python", 1)[0] + "exit 77\n")
    env = {**os.environ, "FT_T17_STAGE": str(tmp_path / "stage"), "FT_T17_SOURCE_ROOT": str(tmp_path / "source"),
           "FT_T17_BATCH": "77", "FT_T17_INPUTS": str(tmp_path / "inputs"), "FT_T17_CLOSURE_BINDING": str(tmp_path / "closure"),
           "FT_T17_SOURCE_REVIEW": str(tmp_path / "review"), "FT_T17_SOURCE_REVIEW_SHA256": "a" * 64,
           "FT_T17_PREFLIGHT_ARTIFACT": str(tmp_path / "preflight"), "FT_T17_ROUNDS": str(tmp_path / "rounds"),
           "FT_T17_CANDIDATE_WORKTREE": str(tmp_path / "worktree")}
    # reserve_and_launch appends --run.  Exit 77 proves the real wrapper passed
    # its argument gate and reached only the substituted exec boundary.
    result = subprocess.run(["bash", template.name, "E2-R035", "--run"], cwd=tmp_path, env=env, capture_output=True)
    assert result.returncode == 77
    rejected = subprocess.run(["bash", template.name, "E2-R035"], cwd=tmp_path, env=env, capture_output=True)
    assert rejected.returncode == 64
