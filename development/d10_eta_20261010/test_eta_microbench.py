import importlib.util
from pathlib import Path

P = Path(__file__).parent / "eta_microbench.py"
spec = importlib.util.spec_from_file_location("eta", P)
eta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eta)

BASE = ["taskset", "-c", "1,3-47", "/data2/FreeToken/venv/bin/ft", "serve", "--model-path", "m", "--moe-strategy", "offload", "--max-running-requests", "2"]

def test_hybrid_diff_is_exact():
    candidate = eta.hybrid_argv(BASE)
    assert candidate[:5] == ["numactl", "--interleave=all", "taskset", "-c", "1,3-23,25,27-47"]
    assert eta.allowed_hybrid_diff(BASE, candidate)
    assert candidate[5:7] == ["/data2/FreeToken/venv/bin/ft", "serve"]
    assert eta.split_server_argv(BASE)[0] == "--model-path" and eta.split_server_argv(candidate)[0] == "--model-path"

def test_slots_exclude_occupied():
    slots = eta.choose_copy_slots(1000, [997, 998, 999], 367)
    assert len(slots) == 367 and not set(slots) & {997, 998, 999}

def test_slots_fail_closed():
    import pytest
    with pytest.raises(RuntimeError):
        eta.choose_copy_slots(2, [0], 2)


def test_graph_slots_are_slot_indices_not_expert_ids():
    class Tensor:
        def detach(self): return self
        def cpu(self): return self
        def tolist(self): return [-1, 29, -1, 7]
    class Cache:
        id_of_slot = Tensor()
    assert eta._graph_slots(Cache()) == [1, 3]


def test_copy_bytes_are_exact_and_fail_closed():
    class Good:
        _copy_feat_bytes_host = [2_000_000, 772_480]
    assert eta._copy_bytes(Good()) == 1_017_500_160
    class Bad:
        _copy_feat_bytes_host = [1]
    import pytest
    with pytest.raises(RuntimeError):
        eta._copy_bytes(Bad())

def test_eta_deviation_blocks_classification():
    assert eta.classify_eta(40, 41.9, 50)["status"] == "REPORT_DEVIATION_BEFORE_ETA"

def test_eta_thresholds():
    assert eta.classify_eta(26.2, 41.9, 30)["verdict"] == "CANDIDATE"
    assert eta.classify_eta(26.2, 41.9, 60)["verdict"] == "CLOSE_D10"


def test_run_gpu_requires_seals_and_frozen_input(tmp_path):
    import pytest
    owner = tmp_path / "owner.json"; owner.write_text('{"argv": ["taskset", "-c", "1,3-47", "/data2/FreeToken/venv/bin/ft", "serve", "--moe-strategy", "offload"]}')
    with pytest.raises(SystemExit):
        eta.main(["--baseline-owner", str(owner), "--run-gpu", "--worktree", str(tmp_path), "--out", str(tmp_path / "out.json")])


def _receipt_payload(schema, **state):
    script_sha = eta.sha256(P)
    return {
        "schema": schema,
        **state,
        "source_pins": {"candidate_commit": eta.EXPECTED_COMMIT, "eta_sha256": script_sha},
        "measure": {"eta_path": eta.ETA_RELATIVE_PATH, "input_x_sha256": eta.EXPECTED_INPUT_SHA},
        "paths_hashes": {"eta_microbench.py": script_sha, "inputs_X.jsonl": eta.EXPECTED_INPUT_SHA},
    }


def _write_readonly(path, payload):
    import json, os
    path.write_text(json.dumps(payload))
    os.chmod(path, 0o444)


def test_sealed_admission_rejects_writable_and_bad_schema(tmp_path):
    import pytest
    receipt = tmp_path / "admission.json"
    receipt.write_text("{}")
    with pytest.raises(RuntimeError, match="regular receipt"):
        eta.validate_admission(receipt)
    _write_readonly(receipt, _receipt_payload(eta.ADMISSION_SCHEMA, admit=True))
    assert eta.validate_admission(receipt) == eta.sha256(receipt)
    import os
    os.chmod(receipt, 0o644)
    receipt.write_text('{"schema":"wrong"}')
    os.chmod(receipt, 0o444)
    with pytest.raises(RuntimeError, match="schema"):
        eta.validate_admission(receipt)


def test_cpu_review_rejects_status_and_source_binding(tmp_path):
    import pytest
    receipt = tmp_path / "review.json"
    _write_readonly(receipt, _receipt_payload(eta.CPU_REVIEW_SCHEMA, status="FAIL"))
    with pytest.raises(RuntimeError, match="status"):
        eta.validate_cpu_review(receipt)
    import os, json
    os.chmod(receipt, 0o644)
    payload = _receipt_payload(eta.CPU_REVIEW_SCHEMA, status="PASS")
    payload["paths_hashes"]["inputs_X.jsonl"] = "wrong"
    receipt.write_text(json.dumps(payload)); os.chmod(receipt, 0o444)
    with pytest.raises(RuntimeError, match="paths_hashes"):
        eta.validate_cpu_review(receipt)


def test_receipt_rejects_symlink(tmp_path):
    import os, pytest
    target = tmp_path / "target.json"
    _write_readonly(target, _receipt_payload(eta.ADMISSION_SCHEMA, admit=True))
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable on this platform")
    with pytest.raises(RuntimeError, match="regular receipt"):
        eta.validate_admission(link)


def test_input_sha_rejects_wrong_file(tmp_path):
    import pytest
    f = tmp_path / "inputs.jsonl"; f.write_text("wrong")
    with pytest.raises(RuntimeError):
        eta.validate_input_sha(f)
