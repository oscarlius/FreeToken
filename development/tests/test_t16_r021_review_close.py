from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

DEV = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, DEV / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path, review, monkeypatch):
    directory = tmp_path / review.RID
    directory.mkdir()
    monkeypatch.setattr(review, "DIRECTORY", directory.resolve())
    receipt = tmp_path / "receipt.json"
    frozen = tmp_path / "t16_d14_runner.py"
    frozen.write_bytes(b"runner")
    monkeypatch.setattr(review, "RUNNER_SHA", review.sha(frozen))
    (tmp_path / "t16_candidate_runner_full_tail.py").write_bytes(b"adapter")
    (tmp_path / "t16_full_tail_base_runner.py").write_bytes(b"base")
    monkeypatch.setattr(review, "ADAPTER_SHA", review.sha(tmp_path / "t16_candidate_runner_full_tail.py"))
    monkeypatch.setattr(review, "BASE_SHA", review.sha(tmp_path / "t16_full_tail_base_runner.py"))
    wrapper = directory / "batch49.sh"
    wrapper.write_bytes(b"wrapper")
    monkeypatch.setattr(review, "WRAPPER_SHA", review.sha(wrapper))
    (directory / "runner_batch49.py").write_bytes(frozen.read_bytes())
    (directory / "base_runner_batch49.py").write_bytes((tmp_path / "t16_full_tail_base_runner.py").read_bytes())
    gate = {"arms": list(review.ARMS), "gate": "D14", "candidate_case": "D14", "parent_commit": review.PARENT, "new_commit": review.CANDIDATE}
    dump(directory / "gate_batch49.json", gate)
    dump(directory / "status_batch49.json", {"rid": review.RID, "batch": 49, "candidate_case": "D14", "state": "complete_measurements_pending_review", "batch_pid": review.BATCH_PID, "batch_start_ticks": review.BATCH_START_TICKS})
    dump(directory / "candidate_binding.json", {"case": "D14", "card": "D14", "parent_wt": "e2base", "new_wt": "e2d14", "parent_commit": review.PARENT, "new_commit": review.CANDIDATE, "ordinary_prefill": False, "candidate_runner_sha256": review.RUNNER_SHA, "base_runner_sha256": review.BASE_SHA})
    dump(receipt, {"schema": "ft_t16_d14_launch/v1", "state": "launched", "rid": review.RID, "batch": 49, "card": "D14", "parent_commit": review.PARENT, "candidate_commit": review.CANDIDATE, "runner_sha256": review.RUNNER_SHA, "base_runner_sha256": review.BASE_SHA, "batch_pid": review.BATCH_PID, "batch_pgid": review.BATCH_PID, "wrapper_sha256": review.WRAPPER_SHA, "frozen_runner": str(frozen)})
    parser = tmp_path / "serve_args_diff.py"
    parser.write_text("def parse(path): return {}\n", encoding="utf-8")
    monkeypatch.setattr(review, "ARGS_PARSER", parser)
    monkeypatch.setattr(hashlib, "md5", lambda data: SimpleNamespace(hexdigest=lambda: "ce123cb0af201d99baac91f7f8e4f8c7"))
    recomputed = {"D0": {"args": {"_unique_suffix": [".pid=1", ".pid=2"]}, "det": {"records": [{"completion_tokens": 128}, {"completion_tokens": 128}]}}, "PROD": {"args": {"_unique_suffix": [".pid=3", ".pid=4"]}, "det": {"records": [{"completion_tokens": 128}, {"completion_tokens": 128}]}}, "prefill": {"parent_rows": 13, "new_rows": 13, "all_prefill_events": 13}}
    gate["layer_major"] = recomputed
    dump(directory / "gate_batch49.json", gate)
    fake_runner = type("Runner", (), {"compare": staticmethod(lambda self, *arms: recomputed)})
    monkeypatch.setattr(review, "import_pinned", lambda *args: SimpleNamespace(CandidateRunner=fake_runner))
    monkeypatch.setattr(review, "terminal", lambda pid, start_ticks=None: True)
    monkeypatch.setattr(review, "service", lambda directory, arm: 1000 + len(arm))
    return directory, receipt


def test_review_requires_terminal_recompute_then_creates_once(tmp_path, monkeypatch):
    review = load("t16_r021_review")
    directory, receipt = fixture(tmp_path, review, monkeypatch)
    result = review.review(directory, receipt)
    assert result["verdict"] == "PASS"
    assert result["recomputed"]["prefill"]["all_prefill_events"] == 13
    assert review.audit(directory, receipt, allow_review=True) == json.loads((directory / "review_batch49.json").read_text())
    with pytest.raises(ValueError, match="unsealed unreviewed"):
        review.review(directory, receipt)


@pytest.mark.parametrize("mutate", ["status", "gate", "tokens", "args"])
def test_review_fails_closed_on_identity_or_recompute_drift(tmp_path, monkeypatch, mutate):
    review = load("t16_r021_review")
    directory, receipt = fixture(tmp_path, review, monkeypatch)
    if mutate == "status":
        dump(directory / "status_batch49.json", {"state": "running"})
    elif mutate == "gate":
        raw = json.loads((directory / "gate_batch49.json").read_text()); raw["arms"] = []; dump(directory / "gate_batch49.json", raw)
    elif mutate == "tokens":
        raw = json.loads((directory / "gate_batch49.json").read_text()); raw["layer_major"]["D0"]["det"]["records"][0]["completion_tokens"] = 127; dump(directory / "gate_batch49.json", raw)
    else:
        raw = json.loads((directory / "gate_batch49.json").read_text()); raw["layer_major"]["D0"]["args"] = {}; dump(directory / "gate_batch49.json", raw)
    with pytest.raises(ValueError):
        review.audit(directory, receipt)
    assert not (directory / "review_batch49.json").exists()


def test_closer_pins_reviewer_source():
    closer = load("t16_r021_close")
    assert closer.REVIEWER_SHA == hashlib.sha256((DEV / "t16_r021_review.py").read_bytes()).hexdigest()
    assert closer.TOOLS["round_close.py"] == "415aa82b34c8fd82d09bfe8a8ce67eed"
