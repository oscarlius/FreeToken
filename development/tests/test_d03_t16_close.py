"""Regression coverage for D03 T16 preparation/closure rollback boundaries."""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="D04 close and PID evidence require Linux")

REPO = Path(__file__).parents[2]
DEVELOPMENT = REPO / "development"
RID = "E2-R002-gate-D03"
BATCH = 41
PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CANDIDATE = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"


def load_close():
    spec = importlib.util.spec_from_file_location("d03_t16_close_under_test", DEVELOPMENT / "d03_t16_close.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def dump(path, value):
    path.write_text(json.dumps(value, allow_nan=False) + "\n", encoding="utf-8")


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_closure_sources(tmp_path):
    root = tmp_path / "root"
    scripts = root / "scripts"
    preparer = root / "runs" / "dev_D03" / "d03_t16_prepare.py"
    scripts.mkdir(parents=True)
    preparer.parent.mkdir(parents=True)
    # The deployed archives are LF.  Re-hash these exact fixture bytes rather
    # than accidentally relying on a local checkout's line-ending conversion.
    def copy_lf(source, target):
        target.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))

    copy_lf(DEVELOPMENT / "d03_t16_prepare.py", preparer)
    for name in ("round_json_append.py", "round_close.py", "round_close.sh"):
        copy_lf(REPO / "scripts" / name, scripts / name)
    return root, preparer


def make_round(tmp_path):
    rounds = tmp_path / "rounds"
    directory = rounds / RID
    directory.mkdir(parents=True)
    arms = [f"{name}_b{BATCH}" for name in ("PARENT", "NEW", "PARENT_P", "NEW_P")]
    for arm_name in arms:
        arm = directory / arm_name
        arm.mkdir()
        for name in ("SERVE_CMD.txt", "serve.log", "det.json", "tax.json", "prefill_seq.txt"):
            (arm / name).write_text("evidence\n", encoding="utf-8")
        if not arm_name.endswith("_P_b" + str(BATCH)):
            (arm / "d0_prefill.jsonl").write_text('{"chunk": 0}\n', encoding="utf-8")
        (arm / "serve_args.txt").write_text(
            "Parsed arguments\n{'_unique_suffix': '.pid=9999999'}\n", encoding="utf-8")
        commit = PARENT if arm_name.startswith("PARENT") else CANDIDATE
        (arm / "ENV.txt").write_text(f"source\n{commit} source\n", encoding="utf-8")
    dump(directory / f"gate_batch{BATCH}.json", {
        "gate": "D03", "proposed_verdict": "kept", "parent_commit": PARENT,
        "new_commit": CANDIDATE, "arms": arms,
        "layer_major": {
            "D0": {"det": {"records": [{"ttft_s": 1.0, "content_chars": 4}]}, "sequence": "SAME"},
            "PROD": {"det": {"records": [{"ttft_s": 2.0, "content_chars": 4}]}, "sequence": "SAME"},
            "prefill": {"parent_rows": 13, "new_rows": 13, "all_prefill_events": 13},
        },
    })
    dump(directory / f"status_batch{BATCH}.json", {
        "gate": "D03", "batch": BATCH, "state": "complete", "batch_pid": 9999999,
        "tools": {"cold_eq.py": "fixture"},
    })
    dump(directory / f"review_batch{BATCH}.json", {"rid": RID, "batch": BATCH, "verdict": "PASS"})
    (directory / f"batch{BATCH}.sh").write_bytes(b"#!/usr/bin/env bash\necho batch\n")
    # Existing byte-exact archive is an original input and must survive rollback.
    (directory / "batch.sh").write_bytes((directory / f"batch{BATCH}.sh").read_bytes())
    (rounds / f"batch{BATCH}.log").write_text("start fixture\n", encoding="utf-8")
    return directory


def configure(module, root, preparer):
    module.PREPARER_SHA = sha(preparer)
    module.TOOLS = {name: md5(root / "scripts" / name)
                    for name in ("round_json_append.py", "round_close.py", "round_close.sh")}


def original_bytes(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def assert_originals_unchanged(directory, original):
    assert original_bytes(directory) == original
    assert not any((directory / name).exists() for name in (
        "initial_metadata.json", "d04_tool_versions.json", "round.json", "round_history", "MANIFEST.sha256",
        "round_json_append.py", "round_close.py", "round_close.sh"))


def test_missing_batch_log_rejects_before_any_write(tmp_path):
    root, preparer = copy_closure_sources(tmp_path)
    directory = make_round(tmp_path)
    (directory.parent / f"batch{BATCH}.log").unlink()
    before = original_bytes(directory)
    close = load_close()
    configure(close, root, preparer)
    with pytest.raises(ValueError, match="batch.*missing|missing or empty"):
        close.close(BATCH, directory, root)
    assert_originals_unchanged(directory, before)


def test_preparer_partial_write_rolls_back_and_retry_closes(tmp_path, monkeypatch):
    root, preparer_path = copy_closure_sources(tmp_path)
    directory = make_round(tmp_path)
    before = original_bytes(directory)
    close = load_close()
    configure(close, root, preparer_path)
    original_spec = close.importlib.util.spec_from_file_location

    class FailingPreparerLoader:
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            source = preparer_path.read_text(encoding="utf-8")
            exec(compile(source, str(preparer_path), "exec"), module.__dict__)
            real_prepare = module.prepare

            def fail_after_prepare(*args, **kwargs):
                real_prepare(*args, **kwargs)
                raise OSError("injected preparer failure")

            module.prepare = fail_after_prepare

    def patched_spec(name, location, *args, **kwargs):
        if name == "d03_t16_prepare":
            return importlib.machinery.ModuleSpec(name, FailingPreparerLoader())
        return original_spec(name, location, *args, **kwargs)

    monkeypatch.setattr(close.importlib.util, "spec_from_file_location", patched_spec)
    with pytest.raises(OSError, match="injected preparer failure"):
        close.close(BATCH, directory, root)
    assert_originals_unchanged(directory, before)
    monkeypatch.setattr(close.importlib.util, "spec_from_file_location", original_spec)
    result = close.close(BATCH, directory, root)
    assert result["formal_verdict"] == "pending_review"
    assert (directory / "MANIFEST.sha256").is_file()


def test_tool_archive_failure_rolls_back_only_new_files(tmp_path, monkeypatch):
    root, preparer = copy_closure_sources(tmp_path)
    directory = make_round(tmp_path)
    before = original_bytes(directory)
    close = load_close()
    configure(close, root, preparer)
    real_write = close.write_exclusive
    calls = 0

    def fail_second_archive(path, data, created):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected archive failure")
        return real_write(path, data, created)

    monkeypatch.setattr(close, "write_exclusive", fail_second_archive)
    with pytest.raises(OSError, match="injected archive failure"):
        close.close(BATCH, directory, root)
    assert_originals_unchanged(directory, before)


def test_preseal_subprocess_failure_rolls_back_only_new_files(tmp_path, monkeypatch):
    root, preparer = copy_closure_sources(tmp_path)
    directory = make_round(tmp_path)
    before = original_bytes(directory)
    close = load_close()
    configure(close, root, preparer)
    monkeypatch.setattr(close.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        subprocess.CalledProcessError(9, a[0])))
    with pytest.raises(subprocess.CalledProcessError):
        close.close(BATCH, directory, root)
    assert_originals_unchanged(directory, before)


def test_postseal_check_failure_retains_closed_evidence(tmp_path, monkeypatch):
    root, preparer = copy_closure_sources(tmp_path)
    directory = make_round(tmp_path)
    close = load_close()
    configure(close, root, preparer)
    real_run = close.subprocess.run

    def fail_only_postseal_check(argv, **kwargs):
        if Path(argv[1]).name == "round_json_append.py" and argv[-1] == "check":
            raise subprocess.CalledProcessError(7, argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(close.subprocess, "run", fail_only_postseal_check)
    with pytest.raises(subprocess.CalledProcessError):
        close.close(BATCH, directory, root)
    assert (directory / "round_history" / "round.v001.json").is_file()
    assert (directory / "MANIFEST.sha256").is_file()
    assert not (directory / "round.json").stat().st_mode & stat.S_IWUSR
