"""Exercise the actual pin reader and canonical D04 checker; no model/network."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SOURCE = Path(__file__).parents[1]


def test_same_directory_checker_is_in_runtime_closure():
    spec = importlib.util.spec_from_file_location('r048_v9_closure', SOURCE / 'r048_t09_prepare_v9.py')
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.HISTORY_CHECKER in tool.RUNTIME_SOURCES
    assert hashlib.sha256(tool.HISTORY_CHECKER.read_bytes()).hexdigest() == '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'


@pytest.fixture
def closed_fixture(tmp_path):
    if sys.platform != 'linux':
        pytest.skip('actual POSIX readonly pin/checker contract runs on Linux')
    capsule = tmp_path / 'capsule'
    capsule.mkdir()
    for name in ('d07_g3g4_prepare.py', 'round_json_append_v1.py'):
        shutil.copyfile(SOURCE / name, capsule / name)
        (capsule / name).chmod(0o444)
    spec = importlib.util.spec_from_file_location('r048_v8_actual_closed', capsule / 'd07_g3g4_prepare.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    reader.ROOT = tmp_path / 'root'
    reader.ROUNDS = tmp_path / 'rounds'
    reader.VENV = Path(sys.executable).parent.parent
    rid = 'E2-R049b'
    directory = reader.ROUNDS / rid
    directory.mkdir(parents=True)
    round_json = directory / 'round.json'
    round_json.write_text(json.dumps({'round_id': rid, 'verdict': 'pending_review'}) + '\n')
    checker = capsule / 'round_json_append_v1.py'
    subprocess.run([sys.executable, str(checker), str(directory), 'verdict', '--new', 'measured', '--reason', 'CPU fixture only', '--evidence', 'fixture', '--by', 'CPU'], check=True, capture_output=True)
    manifest = directory / 'MANIFEST.sha256'
    directory.chmod(0o700)
    manifest.write_text(reader.sha256(round_json) + '  round.json\n')
    manifest.chmod(0o444)
    directory.chmod(0o555)
    pin = reader.ROOT / 'runs/plan_batches/closed_round_pins' / (rid + '.json')
    pin.parent.mkdir(parents=True)
    value = {'rid': rid, 'round_json_sha256': reader.sha256(round_json), 'manifest_sha256': reader.sha256(manifest)}
    pin.write_text(json.dumps(value) + '\n')
    pin.chmod(0o444)
    yield reader, directory, pin, value, checker
    # Restore only this fixture's modes so pytest can remove its own temporary tree.
    for path in tmp_path.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o700 if path.is_dir() else 0o600)


def rewrite_pin(pin, value):
    pin.chmod(0o600)
    pin.write_text(json.dumps(value) + '\n')
    pin.chmod(0o444)


@pytest.mark.parametrize('shape', ['canonical', 'legacy', 'both'])
def test_actual_reader_runs_canonical_checker(closed_fixture, shape):
    reader, directory, pin, value, checker = closed_fixture
    if shape in ('legacy', 'both'):
        value['round_sha256'] = value['round_json_sha256']
    if shape == 'legacy':
        del value['round_json_sha256']
    rewrite_pin(pin, value)
    assert reader.require_closed_round('E2-R049b', 'measured') == directory / 'round.json'
    assert checker.stat().st_mode & 0o222 == 0


@pytest.mark.parametrize('bad', ['conflict', 'missing', 'malformed', 'wrong_rid', 'manifest', 'checker_writable', 'checker_replaced', 'checker_symlink', 'history'])
def test_actual_contract_rejects_invalid_bindings(closed_fixture, bad):
    reader, directory, pin, value, checker = closed_fixture
    if bad == 'conflict':
        value['round_sha256'] = 'f' * 64
    elif bad == 'missing':
        del value['round_json_sha256']
    elif bad == 'malformed':
        value['round_json_sha256'] = 7
    elif bad == 'wrong_rid':
        value['rid'] = 'E2-R049a'
    elif bad == 'manifest':
        value['manifest_sha256'] = 'f' * 64
    elif bad == 'checker_writable':
        checker.chmod(0o600)
    elif bad == 'checker_replaced':
        checker.chmod(0o600)
        checker.write_text('raise AssertionError("replaced checker must not execute")\n')
        checker.chmod(0o444)
    elif bad == 'checker_symlink':
        replacement = checker.with_name('substitute.py')
        shutil.copyfile(checker, replacement)
        replacement.chmod(0o444)
        checker.unlink()
        checker.symlink_to(replacement)
    elif bad == 'history':
        sums = directory / 'round_history/SHA256SUMS'
        sums.chmod(0o600)
        sums.write_text('invalid history\n')
        sums.chmod(0o444)
    rewrite_pin(pin, value)
    with pytest.raises(RuntimeError):
        reader.require_closed_round('E2-R049b', 'measured')
