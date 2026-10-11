from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

DEV = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, DEV / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path, prep):
    directory = tmp_path / prep.RID
    directory.mkdir()
    prep.CANONICAL_ROUND = directory.resolve()
    for arm in prep.ARMS:
        path = directory / arm
        path.mkdir()
        for name in ("SERVE_CMD.txt", "serve.log", "tax.json", "prefill_seq.txt", "det.json"):
            (path / name).write_text("x", encoding="utf-8")
        (path / "serve_args.txt").write_text("{'_unique_suffix': '.pid=999999'}", encoding="utf-8")
        (path / "ENV.txt").write_text(prep.PARENT if arm.startswith("PARENT") else prep.CANDIDATE, encoding="utf-8")
    gate = {"arms": list(prep.ARMS), "gate": "D06", "candidate_case": "D06", "parent_commit": prep.PARENT, "new_commit": prep.CANDIDATE,
            "layer_major": {"D0": {"det": {"records": [{"ttft_s": 1.0}]}, "sequence": "SAME"}, "PROD": {"det": {"records": [{"ttft_s": 2.0}]}, "sequence": "SAME"}, "prefill": {"parent_rows": 13, "new_rows": 13}}}
    write(directory / "gate_batch48.json", gate); prep.RAW_SHA = prep.sha(directory / "gate_batch48.json")
    write(directory / "status_batch48.json", {"state": "complete_measurements_pending_review", "batch": 48, "rid": prep.RID, "candidate_case": "D06", "batch_pid": 3817162})
    (directory / "runner_batch48.py").write_bytes(b"runner")
    (directory / "base_runner_batch48.py").write_bytes(b"base")
    prep.RUNNER_SHA = prep.sha(directory / "runner_batch48.py"); prep.BASE_SHA = prep.sha(directory / "base_runner_batch48.py")
    binding = {"case": "D06", "card": "D06", "parent_wt": "e2base", "new_wt": "e2d06", "parent_commit": prep.PARENT, "new_commit": prep.CANDIDATE, "ordinary_prefill": False, "base_runner_filename": "t16_full_tail_base_runner.py", "candidate_runner_sha256": prep.RUNNER_SHA, "base_runner_sha256": prep.BASE_SHA}
    write(directory / "candidate_binding.json", binding); prep.BINDING_SHA = prep.sha(directory / "candidate_binding.json")
    (directory / "batch48.sh").write_bytes(b"wrapper"); prep.WRAPPER_SHA = prep.sha(directory / "batch48.sh")
    prep.RECEIPT_PATH = tmp_path / "receipt.json"
    receipt = {"schema": "ft_candidate_gate_launch/v1", "state": "launched", "rid": prep.RID, "batch": 48, "case": "D06", "card": "D06", "candidate_commit": prep.CANDIDATE, "parent_commit": prep.PARENT, "runner_sha256": prep.RUNNER_SHA, "base_runner_sha256": prep.BASE_SHA, "wrapper_sha256": prep.WRAPPER_SHA, "batch_pid": 3817162, "batch_pgid": 3817162}
    write(prep.RECEIPT_PATH, receipt); prep.RECEIPT_SHA = prep.sha(prep.RECEIPT_PATH)
    review = {"schema": "ft_independent_raw_review/v1", "reviewer": "/root/d06_server_review", "scope": "raw measurement replay and source integrity; not formal acceptance", "verdict": "PASS", "formal_verdict": "pending_review", "rid": prep.RID, "batch": 48, "batch_pid": 3817162, "parent_commit": prep.PARENT, "candidate_commit": prep.CANDIDATE, "gate_sha256": prep.RAW_SHA, "candidate_binding_sha256": prep.BINDING_SHA, "receipt_sha256": prep.RECEIPT_SHA, "runner_sha256": prep.RUNNER_SHA, "base_runner_sha256": prep.BASE_SHA, "wrapper_sha256": prep.WRAPPER_SHA}
    write(directory / "review_batch48.json", review); prep.REVIEW_SHA = prep.sha(directory / "review_batch48.json")
    return directory


def test_prepare_writes_pending_metadata_and_four_arms(tmp_path):
    prep = load("t16_r020_prepare"); directory = fixture(tmp_path, prep)
    result = prep.prepare(directory, directory / "review_batch48.json")
    meta = json.loads((directory / "initial_metadata.json").read_text())
    assert meta["parent"] == "E2-pre-gate-D00"
    assert meta["base"]["code_version"] == "E2-base@23f2e2c"
    assert meta["verdict"] == "pending_review" and meta["proposed_verdict"] is None
    assert len(meta["serve"]["arms"]) == 4 and result["batch_sha256"] == prep.sha(directory / "batch.sh")


@pytest.mark.parametrize("fault", ["canonical", "review", "raw", "binding", "status", "arms", "ordinary", "env", "live", "alias", "runner", "receipt"])
def test_prepare_fail_closed_for_baseline_contracts(tmp_path, monkeypatch, fault):
    prep = load("t16_r020_prepare"); directory = fixture(tmp_path, prep)
    if fault == "canonical":
        prep.CANONICAL_ROUND = tmp_path / "other"
    elif fault == "review":
        review = json.loads((directory / "review_batch48.json").read_text()); review["verdict"] = "FAIL"; write(directory / "review_batch48.json", review)
    elif fault == "raw":
        (directory / "gate_batch48.json").write_text("{}", encoding="utf-8")
    elif fault == "binding":
        (directory / "candidate_binding.json").write_text("{}", encoding="utf-8")
    elif fault == "status":
        write(directory / "status_batch48.json", {"state": "complete"})
    elif fault == "arms":
        gate = json.loads((directory / "gate_batch48.json").read_text()); gate["arms"] = gate["arms"][:3]; write(directory / "gate_batch48.json", gate); prep.RAW_SHA = prep.sha(directory / "gate_batch48.json")
    elif fault == "ordinary":
        gate = json.loads((directory / "gate_batch48.json").read_text()); gate["non_layer_major"] = {}; write(directory / "gate_batch48.json", gate); prep.RAW_SHA = prep.sha(directory / "gate_batch48.json")
    elif fault == "env":
        (directory / "NEW_b48" / "ENV.txt").write_text(prep.PARENT, encoding="utf-8")
    elif fault == "live":
        monkeypatch.setattr(prep, "terminal", lambda _: False)
    elif fault == "alias":
        (directory / "batch.sh").write_bytes(b"different")
    elif fault == "runner":
        (directory / "runner_batch48.py").write_bytes(b"changed")
    else:
        receipt = json.loads(prep.RECEIPT_PATH.read_text()); receipt["batch"] = 99; write(prep.RECEIPT_PATH, receipt); prep.RECEIPT_SHA = prep.sha(prep.RECEIPT_PATH)
    with pytest.raises((ValueError, FileExistsError)):
        prep.prepare(directory, directory / "review_batch48.json")
    assert not (directory / "initial_metadata.json").exists()


def test_review_sha_must_be_pinned(tmp_path):
    prep = load("t16_r020_prepare"); directory = fixture(tmp_path, prep); prep.REVIEW_SHA = None
    with pytest.raises(ValueError, match="not pinned"):
        prep.prepare(directory, directory / "review_batch48.json")


def test_preparer_and_d04_tool_pins_are_private_and_exact():
    closer = load("t16_r020_close")
    assert closer.PREPARER_SHA == hashlib.sha256((DEV / "t16_r020_prepare.py").read_bytes()).hexdigest()
    assert closer.TOOLS["round_json_append.py"] == "88178a9a3c83dec204e90e6dcf8c4db9"
    assert closer.TOOLS["round_close.py"] == "415aa82b34c8fd82d09bfe8a8ce67eed"
