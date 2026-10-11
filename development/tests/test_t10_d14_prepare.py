import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / 't10_d14_prepare.py'
SPEC = importlib.util.spec_from_file_location('t10_d14_prepare', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def record():
    return MODULE.proposal('a' * 40, {'runner.py': 'b' * 64, 'launcher.py': 'c' * 64})


def test_valid_cpu_only_proposal_preserves_r017_shape():
    value = record()
    MODULE.validate(value)
    assert value['execution'] == 'CPU-preparation-only'
    assert value['inputs']['terminal_records'] == 72
    assert value['inputs']['streams'] == {'B1': ['cold', 'warm'], 'B2': ['cold', 'warm'], 'B3': ['cold', 'warm']}


@pytest.mark.parametrize('mutate', [
    lambda item: item['source'].update(candidate_commit=MODULE.R017['candidate_commit']),
    lambda item: item['flags'].update(prefill_layer_major=True),
    lambda item: item['inputs'].update(terminal_records=71),
    lambda item: item['inputs'].update(frontend_manifest_sha256='d' * 64),
    lambda item: item['inputs'].update(reverse_trace_sha256='d' * 64),
    lambda item: item['probes'].update(terminal_binding=['prompt_ids']),
    lambda item: item['probes'].update(comparison='cold/cold only'),
])
def test_validation_fails_closed_for_protocol_drift(mutate):
    value = record()
    mutate(value)
    with pytest.raises(ValueError):
        MODULE.validate(value)


def test_proposal_rejects_affected_commit_and_missing_source_bundle():
    with pytest.raises(ValueError):
        MODULE.proposal(MODULE.R017['candidate_commit'], {'runner.py': 'a' * 64})
    with pytest.raises(ValueError):
        MODULE.proposal('a' * 40, {})
