import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


DEV = Path(__file__).parents[1]


def load(name='r060_owned'):
    path = DEV / 'r060_oom_owned_launch_v2.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_r060_plan_is_full_four_arm_five_rep_closure():
    spec = importlib.util.spec_from_file_location('r060_prepare', DEV / 'r060_oom_t16_prepare_v1.py')
    module = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module)
    value = module.plan('a' * 40, DEV)
    assert len(value['arms']) == 4
    assert value['multi_probe'] == {'same_prompt': True, 'reps': 5, 'completion_tokens_each': 128,
                                    'ordinary_sidecar_required': True}


def test_r060_admission_requires_dry_review_and_pin_before_reservation(tmp_path, monkeypatch):
    module = load('r060_admission_runtime')
    if sys.platform == 'win32':
        with pytest.raises(RuntimeError):
            module.require_admission()
        return
    dry, review_dir = tmp_path / 'dry.json', tmp_path / 'review'
    review_dir.mkdir(); review, pin = review_dir / 'review.json', review_dir / 'pin.json'
    hashes = {'source.py': 'f' * 64}
    monkeypatch.setattr(module, 'dry_receipt', lambda: dry)
    monkeypatch.setattr(module, 'REVIEW_DIR', review_dir)
    monkeypatch.setattr(module, 'source_hashes', lambda: hashes)
    monkeypatch.setattr(module.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(module.os, 'getcwd', lambda: '/data2/FreeToken')
    payload = {'schema': 'ft_r060_file_dry/v2', 'rid': module.RID, 'candidate_commit': module.CANDIDATE,
               'parent_commit': module.BASE, 'script': str(Path(module.__file__).resolve()), 'cwd': '/data2/FreeToken',
               'uid': 1000, 'source_sha256': hashes, 'passed': True, 'formal_rid_directory_created': False,
               'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False,
               'batch_allocated': False, 'popen_reached': False}
    dry.write_text(json.dumps(payload)); review.write_text(json.dumps({'schema': 'ft_r060_startup_review/v1', 'rid': module.RID,
        'candidate_commit': module.CANDIDATE, 'parent_commit': module.BASE, 'approved': True, 'verdict': 'PASS',
        'source_sha256': hashes, 'file_dry_sha256': hashlib.sha256(dry.read_bytes()).hexdigest()}))
    pin.write_text(json.dumps({'schema': 'ft_r060_startup_review_pin/v1', 'rid': module.RID,
                               'review_sha256': hashlib.sha256(review.read_bytes()).hexdigest()}))
    dry.chmod(0o444); review.chmod(0o444); pin.chmod(0o444)
    assert module.require_admission()['file_dry_sha256'] == hashlib.sha256(dry.read_bytes()).hexdigest()


def test_r060_admission_fails_closed_without_sealed_receipt_or_review(tmp_path, monkeypatch):
    module = load('r060_missing_admission')
    monkeypatch.setattr(module, 'dry_receipt', lambda: tmp_path / 'missing-dry.json')
    monkeypatch.setattr(module, 'REVIEW_DIR', tmp_path / 'missing-review')
    with pytest.raises(RuntimeError, match='FILEDRY/R review/pin'):
        module.require_admission()


def test_r060_child_argv_cannot_drop_owned_receipt():
    module = load('r060_child_argv_runtime')
    argv = module.child_argv(97, Path('/tmp/receipt.json'))
    assert argv[-5:-1] == ['--owned-child', '--batch', '97', '--launch-receipt']
    assert '--run' in argv and Path(argv[-1]).name == 'receipt.json'


def test_r060_runtime_copy_contract_requires_private_0600(tmp_path, monkeypatch):
    module = load('r060_copy_runtime')
    source = tmp_path / 'owned.py'; source.write_text('pass\n')
    monkeypatch.setattr(module, 'source_hashes', lambda: {str(source): hashlib.sha256(source.read_bytes()).hexdigest()})
    monkeypatch.setattr(module, 'check_source', lambda _: None)
    rows = module.copy_runtime_sources(tmp_path / 'copies')
    assert rows[0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    if sys.platform != 'win32': assert (tmp_path / 'copies' / 'owned.py').stat().st_mode & 0o777 == 0o600
