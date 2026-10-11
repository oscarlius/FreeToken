import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).parents[1] / "t17_continuation_close.py"
SPEC = importlib.util.spec_from_file_location("t17_continuation_close", SOURCE)
close = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(close)


def canonical_round_close():
    scripts = SOURCE.parent / "d04_tools"
    if not scripts.is_dir():
        scripts = SOURCE.parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location("t17_test_round_close", scripts / "round_close.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def readonly(path, text=None):
    if text is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    path.chmod(0o444)


def test_validate_stage_requires_bound_cpu_pass_and_frozen_sources(tmp_path):
    stage = tmp_path / "stage"; stage.mkdir()
    files = {}
    for name in close.STAGE_FILES:
        path = stage / name
        if name == "t17_continuation_close.py":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(SOURCE.read_bytes())
            path.chmod(0o444)
        else:
            readonly(path, "# frozen\n")
        files[name] = close.sha(path)
    log = stage / "regression.log"; readonly(log, "4 passed\n")
    report = {"schema": close.STAGE_SCHEMA, "verdict": "PASS", "gpu_started": False, "requests_sent": False,
              "d04_tools": close.TOOLS, "files": files, "step": {"returncode": 0, "log_sha256": close.sha(log)}}
    report_path = stage / "cpu_validation.json"; readonly(report_path, json.dumps(report))
    stage.chmod(0o555)
    observed, digest = close.validate_stage(stage)
    assert observed["files"] == files and digest == close.sha(report_path)

    stage.chmod(0o755); (stage / "regression.log").chmod(0o644)
    with pytest.raises(ValueError, match="immutable auditor stage"):
        close.validate_stage(stage)


def test_audit_rejects_live_or_unidentified_batch_before_reviewer_runs(tmp_path, monkeypatch):
    directory = tmp_path / "E2-R033"; directory.mkdir()
    status = directory / "status_batch61.json"
    readonly(status, json.dumps({"rid": "E2-R033", "batch": 61, "batch_pid": 17}))
    identity = tmp_path / "launch_identity.json"
    readonly(identity, json.dumps({"pid": 17, "pgid": 17, "launch_receipt_sha256": "x" * 64}))
    invoked = []
    monkeypatch.setattr(close, "validate_stage", lambda _: ({}, "stage"))
    monkeypatch.setattr(close, "frozen_auditor", lambda *_: invoked.append(True))
    with pytest.raises(ValueError, match="identity fields are incomplete"):
        close.audit(directory, tmp_path / "stage", tmp_path / "review.json", identity)
    assert not invoked
    assert not (directory / "round.json").exists()


def test_audit_requires_exact_frozen_recomputation_and_stage_bound_json(tmp_path, monkeypatch):
    directory = tmp_path / "E2-R033"; directory.mkdir()
    receipts = tmp_path / "receipts"; receipts.mkdir()
    batch_log = tmp_path / "batch61.log"; batch_log.write_text("batch\n")
    receipt = receipts / "launch_E2-R033.json"
    readonly(receipt, json.dumps({"state": "launched", "rid": "E2-R033", "batch": 61,
                                  "batch_pid": 17, "batch_pgid": 17, "batch_log": str(batch_log)}))
    identity = tmp_path / "launch_identity.json"
    readonly(identity, json.dumps({"pid": 17, "start_ticks": 99, "pgid": 17,
                                   "launch_receipt_sha256": close.sha(receipt)}))
    status = directory / "status_batch61.json"
    # Measurement raw files remain writable until D04 seals the round.
    status.write_text(json.dumps({"rid": "E2-R033", "batch": 61, "batch_pid": 17, "state": "failed"}))
    warm = directory / "first-warm"; warm.mkdir()
    for name in ("SERVE_CMD.txt", "ENV.txt", "serve.log", "compiled_extensions.json", "serve_args.txt"):
        (warm / name).write_text(name + "\n")
    expected = {"schema": "ft_t17_continuation_independent_audit/v1", "verdict": "not_met",
                "launch_receipt_sha256": close.sha(receipt), "actual_status_sha256": close.sha(status)}
    saved = tmp_path / "review.json"; readonly(saved, json.dumps(expected))
    monkeypatch.setattr(close, "terminal", lambda _: None)
    monkeypatch.setattr(close, "LAUNCH_RECEIPTS", receipts)
    monkeypatch.setattr(close, "validate_stage", lambda _: ({"audit_sha256": close.sha(saved)}, "stage-sha"))
    monkeypatch.setattr(close, "frozen_auditor", lambda *_: SimpleNamespace(audit=lambda *_: expected))
    packet = close.audit(directory, tmp_path / "stage", saved, identity)
    assert packet["final_verdict"] == "not_met" and packet["review_sha256"] == close.sha(saved)

    saved.chmod(0o644); saved.write_text(json.dumps({**expected, "verdict": "failed_harness"})); saved.chmod(0o444)
    with pytest.raises(ValueError, match="independent audit JSON differs"):
        close.audit(directory, tmp_path / "stage", saved, identity)


def test_close_fails_before_any_write_when_audit_rejects(tmp_path, monkeypatch):
    directory = tmp_path / "E2-R033"; directory.mkdir()
    monkeypatch.setattr(close, "audit", lambda *_: (_ for _ in ()).throw(ValueError("bad frozen audit")))
    monkeypatch.setattr(close, "verify_tools", lambda: (_ for _ in ()).throw(AssertionError("must not run")))
    with pytest.raises(ValueError, match="bad frozen audit"):
        close.close(directory, tmp_path / "stage", tmp_path / "review", tmp_path / "launch", execute=True)
    assert list(directory.iterdir()) == []


def test_real_d04_validator_accepts_declared_arms_and_cold_missing_args(tmp_path):
    directory = tmp_path / "E2-R033"; directory.mkdir()
    status = directory / "status_batch61.json"
    status.write_text(json.dumps({"rid": "E2-R033", "state": "failed", "error": "cold loading failed"}))
    for arm, args in (("first-warm", True), ("first-reference-1", True), ("first-reference-2", True), ("first-cold-loading", False)):
        path = directory / arm; path.mkdir()
        for name in ("SERVE_CMD.txt", "ENV.txt", "serve.log", "compiled_extensions.json"):
            (path / name).write_text(name + "\n")
        if args:
            (path / "serve_args.txt").write_text("{}\n")
    arms, failure = close.service_evidence(directory, status, "failed_harness")
    batch_log = tmp_path / "batch61.log"; batch_log.write_text("batch\n")
    launch = tmp_path / "identity.json"; launch.write_text("{}")
    receipt = tmp_path / "receipt.json"; receipt.write_text("{}")
    packet = {"receipt": {"rid": "E2-R033", "batch": 61, "candidate_commit": "candidate"},
              "review": {"verdict": "failed_harness"}, "review_sha256": "a" * 64,
              "stage_report_sha256": "b" * 64, "launch_identity": launch, "launch_receipt_path": receipt,
              "service_arms": arms, "failure_archive": failure, "batch_log": batch_log,
              "batch_log_sha256": close.sha(batch_log), "original_raw_files": {}}
    document = close.metadata({**packet, "final_verdict": "failed_harness"})
    (directory / "batch.sh").write_text("#!/usr/bin/env bash\n")
    (directory / "round.json").write_bytes(close.encoded(document))
    prepared = canonical_round_close().prepare(directory)
    assert document["serve"]["arms"] == arms
    assert prepared[0] == directory


def test_close_runs_pinned_d04_seal_then_append_then_check_without_replacing_raw(tmp_path, monkeypatch):
    directory = tmp_path / "E2-R034"; directory.mkdir()
    raw = directory / "raw.txt"; raw.write_text("original")
    batch = directory / "batch.sh"; batch.write_text("#!/usr/bin/env bash\n")
    tools_dir = directory / "source_tools"; tools_dir.mkdir(); (tools_dir / "runner.py").write_text("frozen")
    launch = tmp_path / "launch.json"; launch.write_text('{"rid":"E2-R034"}')
    receipt = tmp_path / "launch_receipt.json"; receipt.write_text('{"rid":"E2-R034"}')
    review = tmp_path / "review.json"; review.write_text('{"verdict":"not_met"}')
    stage = tmp_path / "stage"; stage.mkdir()
    batch_log = tmp_path / "batch62.log"; batch_log.write_text("batch\n")
    original = close.raw_files(directory)
    packet = {"directory": directory, "receipt": {"rid": "E2-R034", "batch": 62, "candidate_commit": "c"},
              "review": {"verdict": "not_met"}, "review_sha256": "a" * 64,
              "stage_report_sha256": "b" * 64, "launch_identity": launch,
              "launch_receipt_path": receipt,
              "stage": stage,
              "service_arms": {"warm": {"files": {}}}, "failure_archive": {"missing_serve_args": []},
              "batch_log": batch_log, "batch_log_sha256": close.sha(batch_log),
              "original_raw_files": original, "final_verdict": "not_met"}
    calls = []
    monkeypatch.setattr(close, "audit", lambda *_: packet)
    monkeypatch.setattr(close, "verify_tools", lambda: {name: b"tool\n" for name in close.TOOLS})
    monkeypatch.setattr(close, "gpu_idle", lambda: calls.append("gpu"))

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "bash":
            lines = []
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.name != "round.json":
                    lines.append(close.sha(path) + "  ./" + path.relative_to(directory).as_posix() + "\n")
            (directory / "MANIFEST.sha256").write_text("".join(lines))
            for path in (directory, *directory.rglob("*")):
                if path.exists(): path.chmod(0o555 if path.is_dir() else 0o444)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(close.subprocess, "run", run)
    result = close.close(directory, stage, review, launch, execute=True)
    assert result["verdict"] == "not_met"
    assert calls[0] == "gpu" and calls[1][0] == "bash"
    assert "--new" in calls[2] and calls[2][calls[2].index("--new") + 1] == "not_met"
    assert calls[3][-1] == "check"
    assert raw.read_text() == "original" and batch.read_text().startswith("#!")
    assert (tools_dir / "runner.py").read_text() == "frozen"
    assert (directory / "review_batch62.json").is_file()


def test_only_allocated_t17_rounds_and_auditor_controls_final_verdict():
    for rid in ("E2-R040", "E2-R041", "E2-R031", "E2-R035-diagnostic"):
        with pytest.raises(ValueError, match="only allocated formal T17 rounds"):
            close.audit(Path(rid), Path("stage"), Path("review"), Path("launch"))
    assert close.verdict_of({"verdict": "kept_pending_independent_review"}) == "kept"
    assert close.verdict_of({"verdict": "failed_harness"}) == "failed_harness"
    with pytest.raises(ValueError, match="closable verdict"):
        close.verdict_of({"verdict": "pending_review"})

def test_formal_r035_and_r039_reach_raw_gate_before_reviewer(monkeypatch, tmp_path):
    for rid in ("E2-R035", "E2-R039"):
        directory = tmp_path / rid; directory.mkdir()
        identity = tmp_path / (rid + ".json")
        readonly(identity, json.dumps({"pid": 1, "start_ticks": 1, "pgid": 1, "launch_receipt_sha256": "x" * 64}))
        monkeypatch.setattr(close, "validate_stage", lambda _: ({}, "stage"))
        with pytest.raises(ValueError, match="regular evidence file|required"):
            close.audit(directory, tmp_path / "stage", tmp_path / "review.json", identity)