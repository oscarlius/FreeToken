from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]
PATH = DEV / "t10_r013_from_r017.py"
SPEC = importlib.util.spec_from_file_location("r013_from_r017", PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_r017_fork_schema_and_actual_final_input_split():
    document = {
        "schema": "t10_engine_tokens/v1",
        "rid": "E2-R017",
        "forkpoints": [
            {
                "prompt_ids": [1, 2],
                "prompt_ids_sha256_int32le": "a",
                "common_generated_ids": [],
                "k": 0,
            }
        ],
    }
    assert runner.unique_forks(document)[0]["prompt_ids"] == [1, 2]
    assert runner.probe_split([1, 2], []) == ([1], [2])
    assert runner.probe_split([1, 2], [3]) == ([1, 2], [3])

    document["rid"] = "E2-R012"
    with pytest.raises(ValueError, match="E2-R017"):
        runner.unique_forks(document)


def test_pinned_parent_validator_rejects_changed_bytes_before_execution(tmp_path):
    source = tmp_path / "validator.py"
    source.write_text("raise AssertionError('should not execute')", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen source changed"):
        runner.load_pinned(source, "0" * 64, "changed")


def test_pinned_parent_validator_loads_exact_reviewed_bytes(tmp_path):
    source = tmp_path / "validator.py"
    source.write_text("value = 17", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    loaded = runner.load_pinned(source, digest, "reviewed")
    assert loaded.value == 17
    assert loaded.__file__ == str(source)


def test_selfcheck_loader_executes_the_same_verified_bytes(monkeypatch, tmp_path):
    source = tmp_path / "d03_gpu_selfcheck.py"
    source.write_text("value = 29", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(runner, "SELFCHECK", source)
    monkeypatch.setattr(runner, "SELFCHECK_SHA", digest)

    loaded = runner.load_sc()

    assert loaded.value == 29
    assert loaded.__file__ == str(source)
    source.write_text("value = 30", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen source changed"):
        runner.load_sc()


def test_capture_rejects_token_filename_uid_when_content_uid_differs(monkeypatch, tmp_path):
    arm = tmp_path / "arm"
    logits = arm / "logits"
    logits.mkdir(parents=True)
    prompt = [11, 12]
    result = {
        "uid": 7,
        "k": 1,
        "input_length": len(prompt),
        "input_sha256": runner.idsha(prompt),
        "positions": [1],
        "dump_seq": 3,
    }
    (logits / "index.jsonl").write_text(
        json.dumps({"kind": "logits", "uid": 7, "seq": 3}) + "\n",
        encoding="utf-8",
    )
    terminal = {
        "schema": "ft_dev_tokens/v1",
        "uid": 8,
        "pid": 55,
        "finish_reason": "stop",
        "prompt_ids": prompt,
        "generated_ids": [13],
        "prompt_length": len(prompt),
        "prompt_ids_sha256_int32le": runner.idsha(prompt),
        "generated_ids_sha256_int32le": runner.idsha([13]),
        "input_ids_sha256_int32le": runner.idsha(prompt + [13]),
    }
    (logits / "tokens_uid7_pid55.json").write_text(json.dumps(terminal), encoding="utf-8")
    (arm / "owned_process.json").write_text(json.dumps({"pgid": 55}), encoding="utf-8")

    def fake_run(argv, **kwargs):
        kwargs["stdout"].write(json.dumps(result) + "\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    run = runner.Run.__new__(runner.Run)

    with pytest.raises(ValueError, match="terminal token does not uniquely bind"):
        run.capture(arm, {}, [11], [12])


def test_runner_frozen_probe_guard_rejects_writable_or_changed_probe(tmp_path):
    probe = tmp_path / "logits_probe.py"
    probe.write_text("value = 'probe'\n", encoding="utf-8")
    digest = hashlib.sha256(probe.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="not read-only"):
        runner.frozen_source(probe, digest)

    probe.chmod(0o444)
    runner.frozen_source(probe, digest)
    probe.chmod(0o644)
    probe.write_text("value = 'changed'\n", encoding="utf-8")
    probe.chmod(0o444)
    with pytest.raises(ValueError, match="frozen source changed"):
        runner.frozen_source(probe, digest)
