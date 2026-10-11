import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load('prepare_r013_parent', DEV / 'd03_phase2_prepare_r013_parent.py')
C = load('close_r013_parent', DEV / 'initial_measurement_close_r013_parent.py')
F = load('phase2_fixture', DEV / 'tests/test_d03_phase2_prepare.py')


def test_preparer_retains_actual_sealed_phase_parent(tmp_path):
    directory, batch = F.t10_phase2_fixture(tmp_path)
    P.prepare(directory, batch, directory / f'review_batch{batch}.json')
    metadata = json.loads((directory / 'initial_metadata.json').read_text())
    admission = json.loads((directory / 'admission.json').read_text())
    assert metadata['parent'] == admission['parent_rid']
    assert metadata['parent'] != 'E2-R000'


def closer_fixture(tmp_path):
    directory, metadata, review = C._fixture(tmp_path, rid='E2-R013')
    admission_path = directory / 'admission.json'
    admission = C.read_json(admission_path)
    proof = directory / 'phase1_round_proof.json'
    proof.write_text(json.dumps({'round_id': 'E2-R017'}) + '\n')
    admission.update(parent_rid='E2-R017', phase1_round_proof_sha256=C.sha(proof))
    admission_path.write_text(json.dumps(admission))
    document = C.read_json(metadata)
    document['parent'] = 'E2-R017'
    metadata.write_text(json.dumps(document))
    return directory, metadata, review


def test_closer_accepts_matching_phase_parent_without_publishing(tmp_path):
    directory, metadata, review = closer_fixture(tmp_path)
    result = C.validate(directory, 'E2-R013', 7, metadata, review, datetime.now(timezone.utc))
    assert result['parent'] == 'E2-R017'
    assert not any((directory / name).exists() for name in C.CONTROL_NAMES)


@pytest.mark.parametrize('fault', ['metadata_parent', 'admission_parent', 'proof_round', 'proof_sha', 'missing_proof'])
def test_closer_rejects_contradictory_phase_parent_before_publication(tmp_path, fault):
    directory, metadata, review = closer_fixture(tmp_path)
    if fault == 'metadata_parent':
        document = C.read_json(metadata); document['parent'] = 'E2-R000'
        metadata.write_text(json.dumps(document))
    elif fault == 'admission_parent':
        path = directory / 'admission.json'; value = C.read_json(path); value['parent_rid'] = 'E2-R016'
        path.write_text(json.dumps(value))
    elif fault == 'proof_round':
        proof = directory / 'phase1_round_proof.json'; proof.write_text(json.dumps({'round_id': 'E2-R016'}))
        path = directory / 'admission.json'; value = C.read_json(path); value['phase1_round_proof_sha256'] = C.sha(proof)
        path.write_text(json.dumps(value))
    elif fault == 'proof_sha':
        path = directory / 'admission.json'; value = C.read_json(path); value['phase1_round_proof_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
    else:
        (directory / 'phase1_round_proof.json').unlink()
    with pytest.raises(ValueError, match='phase parent'):
        C.validate(directory, 'E2-R013', 7, metadata, review, datetime.now(timezone.utc))
    assert not any((directory / name).exists() for name in C.CONTROL_NAMES)
