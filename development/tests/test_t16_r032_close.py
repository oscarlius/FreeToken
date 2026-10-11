import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).parents[1] / 't16_r032_close.py'
SPEC = importlib.util.spec_from_file_location('r032_close', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _packet(tmp_path):
    receipt = tmp_path / 'receipt.json'; receipt.write_text('{}')
    return {'directory': tmp_path, 'receipt_path': receipt, 'receipt': {}, 'review_sha256': 'r' * 64,
            'raw_files': {'gate_batch60.json': 'g' * 64},
            'review': {'service_pids': {arm: index for index, arm in enumerate(MODULE.ARMS, 1)},
                       'gate_sha256': 'g' * 64, 'recomputed': {'layer_major': {}, 'non_layer_major': {}}}}


def test_raw_map_excludes_only_closure_control_files(tmp_path):
    (tmp_path / 'gate_batch60.json').write_text('raw')
    (tmp_path / 'round.json').write_text('new')
    (tmp_path / 'review_batch60.json').write_text('new')
    assert MODULE.raw_files(tmp_path) == {'gate_batch60.json': MODULE.sha(tmp_path / 'gate_batch60.json')}


def test_close_is_audit_first_only_without_explicit_execute(monkeypatch, tmp_path):
    packet = _packet(tmp_path)
    monkeypatch.setattr(MODULE, 'audit_first', lambda: packet)
    result = MODULE.close()
    assert result['state'] == 'audit_first_only'
    assert result['packet'] is packet
    assert not (tmp_path / 'round.json').exists()


def test_metadata_is_eight_arm_t16_and_keeps_t17_d17_out_of_acceptance(monkeypatch, tmp_path):
    log = tmp_path / 'batch60.log'; log.write_text('log')
    monkeypatch.setattr(MODULE, 'ROUNDS', tmp_path)
    packet = _packet(tmp_path)
    doc = MODULE.metadata(packet)
    assert doc['card'] == 'T16'
    assert doc['title'] == 'D14 schedule eight-arm default-path gate'
    assert doc['parent'] == 'E2-R022-gate-D14'
    assert doc['verdict'] == 'pending_review'
    assert doc['results'] == packet['review']['recomputed']
    assert list(doc['serve']['arms']) == list(MODULE.ARMS)
    assert any('T17 and D17 remain pending' in item for item in doc['acceptance_limits'])


def test_close_refuses_to_mutate_when_audit_packet_cannot_be_produced(monkeypatch):
    monkeypatch.setattr(MODULE, 'audit_first', lambda: (_ for _ in ()).throw(ValueError('wrong review')))
    with pytest.raises(ValueError, match='wrong review'):
        MODULE.close(execute=True)


def test_explicit_close_requires_a_dedicated_immutable_stage(monkeypatch, tmp_path):
    packet = _packet(tmp_path)
    monkeypatch.setattr(MODULE, 'audit_first', lambda: packet)
    with pytest.raises(ValueError, match='immutable closure stage'):
        MODULE.close(execute=True)


def test_explicit_close_requires_a_matching_audit_receipt(monkeypatch, tmp_path):
    packet = _packet(tmp_path)
    monkeypatch.setattr(MODULE, 'audit_first', lambda: packet)
    monkeypatch.setattr(MODULE, 'validate_closure_stage', lambda stage: {})
    with pytest.raises(ValueError, match='explicit independent audit receipt'):
        MODULE.close(execute=True, closure_stage=tmp_path)


def test_closure_source_list_is_bounded_and_never_development_tree():
    assert MODULE.CLOSURE_FILES == (
        't16_r032_close.py', 't16_r032_close_stage.py',
        'tests/test_t16_r032_close.py', 'stage_program.py',
        'round_json_append.py', 'round_close.py', 'round_close.sh')
    assert 'HERE' not in MODULE._copy_verified.__code__.co_names
