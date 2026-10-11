from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


DEVELOPMENT = Path(__file__).parents[1]
RID, BATCH = "E2-R014", 52
PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CANDIDATE = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"


def load_module():
    spec = importlib.util.spec_from_file_location("d03_phase2_prepare_test", DEVELOPMENT / "d03_phase2_prepare.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PREPARE = load_module()


def write(path, value):
    path.write_text(json.dumps(value, allow_nan=False) + "\n", encoding="utf-8")


def manifest(directory):
    entries = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "RUN_MANIFEST.sha256"):
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(directory).as_posix()}\n")
    (directory / "RUN_MANIFEST.sha256").write_text("".join(entries), encoding="utf-8")


def fixture(tmp_path):
    directory = tmp_path / RID
    directory.mkdir()
    for arm in ("candidate_boundary", "restore", "recompute", "legal"):
        item = directory / arm
        item.mkdir()
        for name in ("SERVE_CMD.txt", "serve.log", "serve_args.txt"):
            (item / name).write_text(name + "\n", encoding="utf-8")
        (item / "ENV.txt").write_text(CANDIDATE + "\n", encoding="utf-8")
        write(item / "owned_process.json", {"pid": 9_999_999, "pgid": 9_999_999})
        prompt, generated = [1, 2, 3, 4], [5]
        digest = lambda values: hashlib.sha256(struct.pack(f"<{len(values)}i", *values)).hexdigest()
        capture = {"k": 1, "input_sha256": digest(prompt), "input_length": 4,
                   "positions": [3], "uid": 1, "dump_seq": 1, "capture_pid": 9_999_999}
        write(item / "capture.json", capture)
        (item / "logits_capture.log").write_text(json.dumps({key: value for key, value in capture.items() if key != "capture_pid"}) + "\n", encoding="utf-8")
        logits = item / "logits"; logits.mkdir()
        write(logits / "index.jsonl", {"kind": "logits", "uid": 1, "seq": 1, "length": 4,
                                          "extra": {"input_prefix_sha256": digest(prompt), "k": 1,
                                                    "input_length": 4, "positions": [3]}})
        write(logits / "tokens_uid1_pid9999999.json", {"schema": "ft_dev_tokens/v1", "uid": 1, "pid": 9_999_999,
                                                         "prompt_ids": prompt, "generated_ids": generated, "prompt_length": 4,
                                                         "finish_reason": "length", "prompt_ids_sha256_int32le": digest(prompt),
                                                         "generated_ids_sha256_int32le": digest(generated), "input_ids_sha256_int32le": digest(prompt + generated)})
    (directory / "logits_compare.json").write_text(
        json.dumps({"bitwise": True, "kl": 0.0, "top1": 1, "nonfinite": "not-a-stat"}) + "\n",
        encoding="utf-8")
    (directory / "batch.sh").write_bytes(b"#!/bin/sh\necho actual\n")
    batch_sha = hashlib.sha256((directory / "batch.sh").read_bytes()).hexdigest()
    full_digest = hashlib.sha256(struct.pack("<4i", 1, 2, 3, 4)).hexdigest()
    write(directory / "admission.json", {"rid": RID, "card": "T04", "batch": BATCH, "commit": PARENT,
                                             "code_version": "E2-base@23f2e2c", "candidate_commit": CANDIDATE,
                                             "batch_wrapper_sha256": batch_sha,
                                             "input": {"k": 1, "prompt_length": 3, "full_input_sha256": full_digest}})
    write(directory / f"status_batch{BATCH}.json", {"rid": RID, "batch": BATCH, "gate": "T04",
                                                       "state": "complete_measurements_pending_review", "batch_pid": 9_999_999,
                                                       "batch_wrapper_sha256": batch_sha})
    write(directory / f"review_batch{BATCH}.json", {"rid": RID, "batch": BATCH, "verdict": "PASS"})
    boundary = directory / "candidate_boundary" / "logits" / "tokens_uid1_pid9999999.json"
    write(directory / "round_metadata.json", {"rid": RID, "status": "complete_measurements_pending_review",
                                                 "arms": {**{name: json.loads((directory / name / "capture.json").read_text()) for name in ("candidate_boundary", "restore", "recompute", "legal")},
                                                          "candidate_boundary_regenerated_x": {"matches_supplied": True},
                                                          "candidate_boundary_terminal": {"path": str(boundary), "sha256": hashlib.sha256(boundary.read_bytes()).hexdigest(), "uid": 1, "pid": 9_999_999}},
                                                 "comparison": {"bitwise": True, "kl": 0.0, "top1": 1, "nonfinite": "not-a-stat"}})
    manifest(directory)
    return directory


def test_t04_prepares_exclusive_metadata_and_byte_exact_wrapper(tmp_path):
    directory = fixture(tmp_path)
    result = PREPARE.prepare(directory, BATCH, directory / f"review_batch{BATCH}.json",
                             now=datetime(2026, 10, 4, tzinfo=timezone(timedelta(hours=8))))
    metadata = json.loads((directory / "initial_metadata.json").read_text(encoding="utf-8"))
    assert result["rid"] == RID
    assert metadata["base"]["commit"] == PARENT
    assert metadata["experimental"]["candidate_commit"] == CANDIDATE
    assert metadata["results"]["numeric"]["comparison.kl"] == 0.0
    assert (directory / "batch.sh").read_bytes() == b"#!/bin/sh\necho actual\n"
    with pytest.raises(ValueError, match="initial metadata"):
        PREPARE.prepare(directory, BATCH, directory / f"review_batch{BATCH}.json")


def test_manifest_mismatch_fails_before_wrapper_or_metadata_write(tmp_path):
    directory = fixture(tmp_path)
    (directory / "round_metadata.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"RUN_MANIFEST(?:\.sha256)? mismatch"):
        PREPARE.prepare(directory, BATCH, directory / f"review_batch{BATCH}.json")
    assert (directory / "batch.sh").exists()
    assert not (directory / "initial_metadata.json").exists()


def test_metadata_serialization_failure_rolls_back_new_wrapper(tmp_path, monkeypatch):
    directory = fixture(tmp_path)
    monkeypatch.setattr(PREPARE, "json_bytes", lambda value: (_ for _ in ()).throw(OSError("injected write failure")))
    with pytest.raises(OSError, match="injected write failure"):
        PREPARE.prepare(directory, BATCH, directory / f"review_batch{BATCH}.json")
    assert (directory / "batch.sh").exists()
    assert not (directory / "initial_metadata.json").exists()


def test_t04_forged_capture_token_is_rejected_even_when_manifest_is_rehashed(tmp_path):
    directory = fixture(tmp_path)
    token = directory / "restore" / "logits" / "tokens_uid1_pid9999999.json"
    forged = json.loads(token.read_text(encoding="utf-8"))
    forged["prompt_ids"] = [9, 9, 9]
    token.write_text(json.dumps(forged) + "\n", encoding="utf-8")
    manifest(directory)
    with pytest.raises(ValueError, match="terminal token ID hashes|terminal token does not bind"):
        PREPARE.prepare(directory, BATCH, directory / f"review_batch{BATCH}.json")


def digest(ids):
    return hashlib.sha256(struct.pack(f"<{len(ids)}i", *ids)).hexdigest()


def t10_arm(directory, name, pid):
    arm = directory / name; arm.mkdir()
    for filename in ("SERVE_CMD.txt", "serve.log", "serve_args.txt"):
        (arm / filename).write_text(filename + "\n", encoding="utf-8")
    (arm / "ENV.txt").write_text(CANDIDATE + "\n", encoding="utf-8")
    write(arm / "owned_process.json", {"pid": pid, "pgid": pid})
    (arm / "logits").mkdir()
    return arm


def t10_phase1_fixture(tmp_path):
    directory = tmp_path / "E2-R012"; directory.mkdir()
    batch = 61
    messages, frontend = [], []
    for index in range(12):
        message = [{"role": "user", "content": f"prompt {index}"}]
        key = hashlib.sha256(json.dumps(message, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        prompt = [100 + index, 200 + index]
        messages.append({"messages": message, "record": {"messages_sha": key}})
        frontend.append({"round": index, "messages_sha": key, "prompt_ids": prompt,
                         "prompt_length": len(prompt), "prompt_ids_sha256_int32le": digest(prompt)})
    write(directory / "frontend_manifest.json", {"schema": "t10_frontend_tokens/v1", "rounds": frontend,
                                                    "candidate_commit": CANDIDATE})
    write(directory / "reverse_trace.json", {"rounds": messages})
    write(directory / "forward_trace.json", {"rounds": messages})
    arms = {}
    fork = None
    for arm_index, name in enumerate(("B1", "B2", "B3")):
        arm = t10_arm(directory, name, 9_008_000 + arm_index)
        phases = {}
        for phase in ("cold", "warm"):
            rows = {}
            for index, source in enumerate(frontend):
                # UIDs are distinct within a service's cold/warm requests;
                # the same UID may occur under a different service PID.
                uid, generated = index + (12 if phase == "warm" else 0), [10, 11]
                if index in (0, 1) and name == "B3" and phase == "warm":
                    generated = [10, 12]
                record = {"schema": "ft_dev_tokens/v1", "uid": uid, "pid": 9_008_000 + arm_index,
                          "prompt_ids": source["prompt_ids"], "generated_ids": generated,
                          "prompt_length": 2, "finish_reason": "length",
                          "prompt_ids_sha256_int32le": digest(source["prompt_ids"]),
                          "generated_ids_sha256_int32le": digest(generated),
                          "input_ids_sha256_int32le": digest(source["prompt_ids"] + generated)}
                path = arm / "logits" / f"tokens_uid{uid}_pid{9_008_000 + arm_index}.json"
                write(path, record)
                rows[source["messages_sha"]] = {"round": index, "messages_sha": source["messages_sha"],
                    "terminal_file": path.name, "terminal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "uid": uid, "pid": 9_008_000 + arm_index, "prompt_ids": source["prompt_ids"], "generated_ids": generated}
            phases[phase] = rows
        arms[name] = phases
    first = frontend[0]
    fork = {"round": 0, "messages_sha": first["messages_sha"], "prompt_ids": first["prompt_ids"],
            "prompt_ids_sha256_int32le": first["prompt_ids_sha256_int32le"], "common_generated_ids": [10],
        "first_difference_index": 1, "k": 1, "observed_next_ids": [11, 11, 11, 11, 11, 12]}
    second = {**fork, "round": 1, "messages_sha": frontend[1]["messages_sha"], "prompt_ids": frontend[1]["prompt_ids"],
              "prompt_ids_sha256_int32le": frontend[1]["prompt_ids_sha256_int32le"]}
    phase_manifest = {"schema": "t10_engine_tokens/v1", "rid": "E2-R012", "arms": arms, "forkpoints": [fork, second],
                      "frontend_manifest_sha256": hashlib.sha256((directory / "frontend_manifest.json").read_bytes()).hexdigest()}
    write(directory / "phase1_manifest.json", phase_manifest)
    wrapper = b"#!/bin/sh\ntrue\n"; (directory / "batch.sh").write_bytes(wrapper); wrapper_sha = hashlib.sha256(wrapper).hexdigest()
    write(directory / "admission.json", {"rid": "E2-R012", "card": "T10", "batch": batch, "commit": PARENT,
        "code_version": "E2-base@23f2e2c", "candidate_commit": CANDIDATE, "batch_wrapper_sha256": wrapper_sha,
        "frontend_manifest_sha256": phase_manifest["frontend_manifest_sha256"],
        "reverse_trace_sha256": hashlib.sha256((directory / "reverse_trace.json").read_bytes()).hexdigest(),
        "forward_trace_sha256": hashlib.sha256((directory / "forward_trace.json").read_bytes()).hexdigest()})
    write(directory / f"status_batch{batch}.json", {"rid": "E2-R012", "batch": batch, "gate": "T10",
        "state": "complete_measurements_pending_review", "batch_pid": 9_999_999, "batch_wrapper_sha256": wrapper_sha})
    write(directory / f"review_batch{batch}.json", {"rid": "E2-R012", "batch": batch, "verdict": "PASS"})
    write(directory / "round_metadata.json", {"rid": "E2-R012", "status": "complete_measurements_pending_review",
                                                 "terminal_records_per_arm": 24, "forkpoints": 2})
    manifest(directory)
    return directory, batch


def test_t10_phase1_accepts_repeated_uid_when_service_pid_differs(tmp_path):
    directory, batch = t10_phase1_fixture(tmp_path)
    # This is a valid producer shape.  Older preparers incorrectly made UID
    # globally unique across services and reject it; the final contract must pass.
    PREPARE.prepare(directory, batch, directory / f"review_batch{batch}.json")
    assert (directory / "initial_metadata.json").is_file()


def seal_phase1(directory, batch):
    """Seal the generated parent through the real D04 implementation."""
    sys.path.insert(0, str(DEVELOPMENT.parent / "scripts"))
    import round_close, round_json_append
    writer_source = DEVELOPMENT.parent / "scripts" / "round_json_append.py"
    (directory / "round_json_append.py").write_bytes(writer_source.read_bytes())
    document = {"schema": "ft_round/v2", "round_id": "E2-R012", "epoch": 2, "card": "T10",
                "verdict": "pending_review", "proposed_verdict": None, "verdict_history": [], "retractions": [],
                "base": {"commit": PARENT, "code_version": "E2-base@23f2e2c"},
                "serve": {"arms": {name: {} for name in ("B1", "B2", "B3")}}, "results": {"records": 72},
                "sub_conclusions": [{"id": "SC1", "text": "phase one", "status": "pending"}]}
    (directory / "round.json").write_bytes(round_json_append.json_bytes(document))
    round_close.close(directory)
    return json.loads((directory / "round.json").read_text())


def t10_phase2_fixture(tmp_path):
    parent, parent_batch = t10_phase1_fixture(tmp_path)
    seal_phase1(parent, parent_batch)
    # Parent is now readonly; the phase-2 consumer is a distinct sibling.
    child = parent.parent / "E2-R013"; child.mkdir()
    batch = 62
    for name in ("phase1_manifest.json",):
        (child / name).write_bytes((parent / name).read_bytes())
    (child / "phase1_round_proof.json").write_bytes((parent / "round.json").read_bytes())
    phase = json.loads((child / "phase1_manifest.json").read_text())
    results = []
    for number, fork in enumerate(sorted(phase["forkpoints"], key=lambda item: item["messages_sha"])):
        fork_subset = {key: fork[key] for key in ("messages_sha", "prompt_ids", "common_generated_ids", "k", "first_difference_index", "observed_next_ids")}
        input_ids = fork_subset["prompt_ids"] + fork_subset["common_generated_ids"]
        captures = []
        for side, pid in (("a", 9_008_101 + number * 10), ("b", 9_008_102 + number * 10)):
            arm = t10_arm(child, f"fork{number:02d}_{side}", pid)
            capture = {"uid": 3 + number, "capture_pid": pid, "dump_seq": 1, "k": 1, "input_sha256": digest(input_ids),
                       "input_length": len(input_ids), "positions": [len(input_ids) - 1]}
            write(arm / "capture.json", capture)
            (arm / "capture.log").write_text(json.dumps({key: value for key, value in capture.items() if key != "capture_pid"}) + "\n", encoding="utf-8")
            logits = arm / "logits"; logits.mkdir(exist_ok=True)
            write(logits / "index.jsonl", {"kind": "logits", "uid": 3 + number, "seq": 1, "length": len(input_ids),
                                         "extra": {"input_prefix_sha256": digest(input_ids), "k": 1,
                                                   "input_length": len(input_ids), "positions": [len(input_ids) - 1]}})
            generated = [99]
            write(logits / f"tokens_uid{3 + number}_pid{pid}.json", {"schema": "ft_dev_tokens/v1", "uid": 3 + number, "pid": pid,
                "prompt_ids": input_ids, "generated_ids": generated, "prompt_length": len(input_ids), "finish_reason": "length",
                "prompt_ids_sha256_int32le": digest(input_ids), "generated_ids_sha256_int32le": digest(generated),
                "input_ids_sha256_int32le": digest(input_ids + generated)})
            captures.append(capture)
        comparison = {"bitwise": True, "kl": 0.0, "input_prefix_sha256": digest(input_ids), "k": 1,
                      "input_length": len(input_ids), "positions": [len(input_ids) - 1]}
        (child / f"fork{number:02d}_compare.log").write_text(json.dumps(comparison) + "\n", encoding="utf-8")
        results.append({"forkpoint": fork_subset, "capture_a": captures[0], "capture_b": captures[1], "comparison": comparison})
    write(child / "stage2_results.json", {"schema": "t10_logits_stage2/v1", "results": results})
    write(child / "round_metadata.json", {"rid": "E2-R013", "status": "complete_measurements_pending_review", "fresh_pairs": 2})
    wrapper = b"#!/bin/sh\ntrue\n"; (child / "batch.sh").write_bytes(wrapper); wrapper_sha = hashlib.sha256(wrapper).hexdigest()
    write(child / "admission.json", {"rid": "E2-R013", "parent_rid": "E2-R012", "card": "T10", "batch": batch,
        "commit": PARENT, "code_version": "E2-base@23f2e2c", "candidate_commit": CANDIDATE, "batch_wrapper_sha256": wrapper_sha,
        "phase1_manifest_sha256": hashlib.sha256((child / "phase1_manifest.json").read_bytes()).hexdigest(),
        "phase1_round_proof_sha256": hashlib.sha256((child / "phase1_round_proof.json").read_bytes()).hexdigest(), "forkpoints": 2})
    write(child / f"status_batch{batch}.json", {"rid": "E2-R013", "batch": batch, "gate": "T10",
        "state": "complete_measurements_pending_review", "batch_pid": 9_999_999, "batch_wrapper_sha256": wrapper_sha})
    write(child / f"review_batch{batch}.json", {"rid": "E2-R013", "batch": batch, "verdict": "PASS"})
    manifest(child)
    return child, batch


def test_t10_phase2_fixture_has_real_sealed_parent_and_rejects_tampering(tmp_path):
    directory, batch = t10_phase2_fixture(tmp_path)
    # Parent was sealed by the real D04 closer, including writer-compatible history.
    assert (directory.parent / "E2-R012" / "MANIFEST.sha256").is_file()
    # Helper acceptance follows after root's P1 composite UID repair; first show
    # that a changed consumed token is rejected even when the child manifest is rehashed.
    token = directory / "fork00_a" / "logits" / "tokens_uid3_pid9008101.json"
    record = json.loads(token.read_text()); record["pid"] = 123
    token.write_text(json.dumps(record) + "\n"); manifest(directory)
    with pytest.raises(ValueError):
        PREPARE.prepare(directory, batch, directory / f"review_batch{batch}.json")


def test_t10_phase2_prepares_valid_sealed_parent(tmp_path):
    directory, batch = t10_phase2_fixture(tmp_path)
    result = PREPARE.prepare(directory, batch, directory / f"review_batch{batch}.json")
    metadata = json.loads((directory / "initial_metadata.json").read_text(encoding="utf-8"))
    assert result["rid"] == "E2-R013"
    assert metadata["verdict"] == "pending_review"
    assert metadata["proposed_verdict"] is None
    assert metadata["card"] == "T10"


def assert_rejected_without_metadata(directory, batch, message):
    with pytest.raises(ValueError, match=message):
        PREPARE.prepare(directory, batch, directory / f"review_batch{batch}.json")
    assert not (directory / "initial_metadata.json").exists()


@pytest.mark.parametrize("fault", ["parent_manifest", "terminal_uid", "same_service", "missing_capture_log", "missing_index", "missing_compare", "manifest_capture", "manifest_index", "manifest_compare", "index_binding", "capture_log", "duplicate_fork"])
def test_t10_phase2_rejects_evidence_tampering(tmp_path, fault):
    directory, batch = t10_phase2_fixture(tmp_path)
    parent = directory.parent / "E2-R012"
    if fault == "parent_manifest":
        manifest_path = parent / "MANIFEST.sha256"
        mode = manifest_path.stat().st_mode
        manifest_path.chmod(mode | 0o200)
        try:
            manifest_path.write_text("0" * 64 + "  ./phase1_manifest.json\n", encoding="utf-8")
        finally:
            manifest_path.chmod(mode)
    elif fault == "terminal_uid":
        path = directory / "fork00_a" / "logits" / "tokens_uid3_pid9008101.json"
        data = json.loads(path.read_text()); data["uid"] = 4; path.write_text(json.dumps(data) + "\n")
        manifest(directory)
    elif fault == "same_service":
        write(directory / "fork00_b" / "owned_process.json", {"pid": 9_008_101, "pgid": 9_008_101})
        manifest(directory)
    elif fault == "missing_capture_log":
        (directory / "fork00_a" / "capture.log").unlink(); manifest(directory)
    elif fault == "missing_index":
        (directory / "fork00_a" / "logits" / "index.jsonl").unlink(); manifest(directory)
    elif fault == "missing_compare":
        (directory / "fork00_compare.log").write_text('{"bitwise": false}\n', encoding="utf-8"); manifest(directory)
    elif fault.startswith("manifest_"):
        manifest_path = directory / "RUN_MANIFEST.sha256"
        target = {"manifest_capture": "fork00_a/capture.log", "manifest_index": "fork00_a/logits/index.jsonl",
                  "manifest_compare": "fork00_compare.log"}[fault]
        lines = [line for line in manifest_path.read_text().splitlines() if not line.endswith(target)]
        manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif fault == "index_binding":
        index = directory / "fork00_a" / "logits" / "index.jsonl"
        data = json.loads(index.read_text()); data["seq"] = 99; write(index, data); manifest(directory)
    elif fault == "capture_log":
        (directory / "fork00_a" / "capture.log").write_text('{"k": 9}\n', encoding="utf-8"); manifest(directory)
    else:
        stage = directory / "stage2_results.json"; data = json.loads(stage.read_text())
        data["results"][1] = data["results"][0]; write(stage, data); manifest(directory)
    assert_rejected_without_metadata(directory, batch, r"(?i)parent|terminal|service|capture|index|compar|manifest|fork")
