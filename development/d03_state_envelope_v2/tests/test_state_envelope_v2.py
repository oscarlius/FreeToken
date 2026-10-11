import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('d03_state_envelope_v2', Path(__file__).parents[1] / 'state_envelope_v2.py')
state = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = state
SPEC.loader.exec_module(state)

torch = pytest.importorskip('torch')


def make_dump(directory, tensor, *, uid='uid-7', prefix='prefix-7', tier='device'):
    directory.mkdir(parents=True)
    roles = state.DEVICE_ROLES if tier == 'device' else state.HOST_ROLES
    files = {}
    for index, role in enumerate(roles):
        name = f'{index}.pt'
        torch.save(tensor.clone(), directory / name)
        files[role] = name
    row = {'kind': 'donate', 'length': 32052, 'seq': 1, 'uid': uid,
           'prefix_hash': prefix, 'files': files}
    (directory / 'index.jsonl').write_text(json.dumps(row) + '\n', encoding='utf-8')


def selected_pair(tmp_path, ref_tensor, test_tensor, **selectors):
    ref, test = tmp_path / 'ref', tmp_path / 'test'
    make_dump(ref, ref_tensor, **selectors)
    make_dump(test, test_tensor, **selectors)
    return state.select_records(ref, 'donate', None, None, None, selectors.get('tier', 'device'), None).records[32052], state.select_records(test, 'donate', None, None, None, selectors.get('tier', 'device'), None).records[32052]


def test_float_and_bfloat16_paired_layers_emit_real_max_abs(tmp_path):
    ref, test = selected_pair(tmp_path / 'float', torch.tensor([[1.0, 2.0], [3.0, 4.0]]),
                              torch.tensor([[1.0, 2.0], [3.0, 4.25]]))
    points = state.paired_metrics(ref, test, 'device')
    assert len(points) == len(state.DEVICE_ROLES) * 2
    assert {point['max_abs'] for point in points} == {0.0, 0.25}

    ref, test = selected_pair(tmp_path / 'bf16', torch.tensor([[1, 2]], dtype=torch.bfloat16),
                              torch.tensor([[1, 3]], dtype=torch.bfloat16))
    assert {point['max_abs'] for point in state.paired_metrics(ref, test, 'device')} == {1.0}


def test_int64_adjacent_values_past_float32_range_keep_exact_delta(tmp_path):
    ref_tensor = torch.tensor([[16_777_217, 9_223_372_036_854_775_806]], dtype=torch.int64)
    test_tensor = torch.tensor([[16_777_218, 9_223_372_036_854_775_807]], dtype=torch.int64)
    ref, test = selected_pair(tmp_path, ref_tensor, test_tensor)
    points = state.paired_metrics(ref, test, 'device')
    assert {point['max_abs'] for point in points} == {1}


def test_int64_boundaries_do_not_overflow_max_abs(tmp_path):
    ref, test = selected_pair(tmp_path, torch.tensor([[-2**63]], dtype=torch.int64),
                              torch.tensor([[2**63 - 1]], dtype=torch.int64))
    assert {point['max_abs'] for point in state.paired_metrics(ref, test, 'device')} == {2**64 - 1}


def test_zero_reference_preserves_old_status_and_emits_max_abs(tmp_path):
    ref, test = selected_pair(tmp_path, torch.zeros((1, 2)), torch.tensor([[0.0, 2.0]]))
    points = state.paired_metrics(ref, test, 'device')
    assert {point['comparison_status'] for point in points} == {'zero_reference_nonzero_delta'}
    assert {point['relative_l2'] for point in points} == {None}
    assert {point['max_abs'] for point in points} == {2.0}


@pytest.mark.parametrize('fault', ('shape', 'dtype', 'uid', 'prefix'))
def test_shape_dtype_and_identity_mismatches_fail_closed(tmp_path, fault):
    ref_dir, test_dir = tmp_path / 'ref', tmp_path / 'test'
    make_dump(ref_dir, torch.ones((1, 2)))
    if fault == 'shape':
        make_dump(test_dir, torch.ones((2, 2)))
    elif fault == 'dtype':
        make_dump(test_dir, torch.ones((1, 2), dtype=torch.int64))
    elif fault == 'uid':
        make_dump(test_dir, torch.ones((1, 2)), uid='other')
    else:
        make_dump(test_dir, torch.ones((1, 2)), prefix='other')
    ref = state.select_records(ref_dir, 'donate', None, None, None, 'device', None).records[32052]
    test = state.select_records(test_dir, 'donate', None, None, None, 'device', None).records[32052]
    with pytest.raises(state.EnvelopeError):
        state.paired_metrics(ref, test, 'device')


def test_csv_writes_exact_int64_max_abs_column(tmp_path):
    ref_dir, test_dir = tmp_path / 'ref', tmp_path / 'test'
    make_dump(ref_dir, torch.tensor([[16_777_217]], dtype=torch.int64))
    make_dump(test_dir, torch.tensor([[16_777_218]], dtype=torch.int64))
    rows, _ = state.compare(ref_dir, test_dir, [])
    output = tmp_path / 'paired.csv'
    state.write_csv(output, rows)
    with output.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(state.DEVICE_ROLES)
    assert set(rows[0]) >= {'max_abs', 'relative_l2', 'unequal_ratio'}
    assert {row['max_abs'] for row in rows} == {'1'}

