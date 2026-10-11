import hashlib
import importlib.util
import base64
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "t16_d14_schedule_stage.py"
SPEC = importlib.util.spec_from_file_location("schedule_stage", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_manifest_uses_the_frozen_engine_receipt_name_and_exact_set():
    identity, files = MODULE.source_manifest()
    assert len(identity) == 64
    assert set(files) == set(MODULE.SOURCE_NAMES)
    assert len(MODULE.SOURCE_NAMES) == len(set(MODULE.SOURCE_NAMES))
    assert MODULE.ENGINE_RECEIPT_FROZEN in files
    assert MODULE.ENGINE_RECEIPT_SOURCE not in files
    assert files[MODULE.ENGINE_RECEIPT_FROZEN] == (
        MODULE._source_path(MODULE.HERE, MODULE.ENGINE_RECEIPT_FROZEN)
    ).read_bytes()
    assert files["stage_program.py"] == MODULE.PROGRAM.encode()


def test_frozen_manifest_round_trip_preserves_renamed_receipt(tmp_path):
    _, files = MODULE.source_manifest()
    for name, data in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    receipt = tmp_path / MODULE.ENGINE_RECEIPT_FROZEN
    assert receipt.is_file()
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == hashlib.sha256(
        MODULE._source_path(MODULE.HERE, MODULE.ENGINE_RECEIPT_FROZEN).read_bytes()
    ).hexdigest()
    assert not (tmp_path / MODULE.ENGINE_RECEIPT_SOURCE).exists()
    identity, roundtrip = MODULE.source_manifest(tmp_path)
    assert roundtrip == files


def test_d18_test_source_is_resolved_from_root_tests_when_not_staged(tmp_path):
    root = tmp_path / "development"
    root.mkdir()
    parent_test = tmp_path / "tests" / "test_d18_client_params.py"
    parent_test.parent.mkdir()
    parent_test.write_text("# D18\n")
    assert MODULE._source_path(root, MODULE.D18_TEST) == parent_test


def test_failed_cpu_step_preserves_actual_log_and_report(tmp_path, monkeypatch):
    destination = tmp_path/'failed'
    raw = b'owned source'
    payload = {'target': str(destination), 'tests': ['sample.py'],
               'files': {'sample.py': base64.b64encode(raw).decode()},
               'source_sha256': {'sample.py': hashlib.sha256(raw).hexdigest()}}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(MODULE.subprocess, 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=1, stdout='actual failure\n', stderr=''))
    try:
        exec(compile(MODULE.PROGRAM, 'stage_program.py', 'exec'), {})
        report = json.loads((destination/'cpu_validation.json').read_bytes())
        assert report['verdict'] == 'FAIL'
        assert report['steps']['regression']['returncode'] == 1
        assert (destination/'regression.log').read_text() == 'actual failure\n'
        assert report['files'] == payload['source_sha256']
        assert 'd18_binding' not in report['steps']
    finally:
        destination.chmod(0o755)
        for path in destination.rglob('*'): path.chmod(0o755 if path.is_dir() else 0o644)


def test_stage_collision_leaves_existing_directory_unchanged(tmp_path, monkeypatch):
    sentinel = tmp_path/'existing'; sentinel.write_bytes(b'foreign owner')
    before = sorted((path.name, path.read_bytes()) for path in tmp_path.iterdir())
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'target': str(tmp_path)})))
    with pytest.raises(FileExistsError):
        exec(compile(MODULE.PROGRAM, 'stage_program.py', 'exec'), {})
    assert sorted((path.name, path.read_bytes()) for path in tmp_path.iterdir()) == before


def test_declared_tests_are_exact_and_do_not_duplicate_launcher():
    assert MODULE.TESTS[-3:] == (
        "tests/test_t16_d14_schedule_runner.py",
        "tests/test_t16_d14_schedule_stage.py",
        "tests/test_t16_d14_schedule_launch.py",
    )
    assert len(MODULE.TESTS) == len(set(MODULE.TESTS))
