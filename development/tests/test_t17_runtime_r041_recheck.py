"""Execution rejects a cached four-case permit after its raw proof is lost."""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def plan(tmp_path):
    source = HERE / 'realinput_28.json'
    if not source.exists():
        pytest.skip('the Linux freeze supplies the SHA-bound real 28-case input')
    selection = load('t17_continuation_selection')
    document = selection.load_realinput28(source)
    inputs = tmp_path / 'real_inputs.json'; inputs.write_bytes(source.read_bytes()); inputs.chmod(0o444)
    selected = selection.select(document, run_kind='t20', cases='t20-sample4',
                                envelope_cases='sample4', assigned_rid='E2-R040')
    value = {'inputs': str(inputs), 'inputs_sha256': selection.INPUTS_SHA256, 'selection': selected,
             'rid': 'E2-R040', 'case_choices': [
                 {'name': name, 'input_ids_sha256': selected['case_input_sha256'][name],
                  'allow_cold_envelope': name in selected['ordinary_cold_envelope_cases']}
                 for name in selected['measurement_cases']]}
    return value, {row['name']: row for row in document['cases']}


def test_all28_selection_revalidates_real_inputs(tmp_path):
    value, cases = plan(tmp_path)
    load('t17_continuation_runtime_v2')._validate_case_choices(value, cases)


def test_cached_permit_without_replay_inputs_is_rejected(tmp_path):
    value, cases = plan(tmp_path)
    value['selection']['r041_proof'] = {'permit': True}
    runtime = load('t17_continuation_runtime_v2')
    with pytest.raises(runtime.RuntimeErrorV2, match='raw-verification inputs'):
        runtime._validate_case_choices(value, cases)


def test_cached_sample4_cannot_survive_missing_raw_closure(tmp_path):
    value, cases = plan(tmp_path)
    selection = load('t17_continuation_selection')
    chosen = value['selection']
    chosen['measurement_cases'] = list(selection.SAMPLE4)
    chosen['case_input_sha256'] = {name: chosen['case_input_sha256'][name] for name in selection.SAMPLE4}
    chosen['r041_proof'] = {'verification_inputs': {
        'r041_round': str(tmp_path / 'missing'), 'expected_verifier_sha256': '0' * 64}}
    value['case_choices'] = [row for row in value['case_choices'] if row['name'] in selection.SAMPLE4]
    runtime = load('t17_continuation_runtime_v2')
    with pytest.raises(runtime.RuntimeErrorV2, match='selection changed'):
        runtime._validate_case_choices(value, cases)
