import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'r049_t21_ordinary_prepare_v11.py'
if not SOURCE.is_file():
    SOURCE = HERE.parent / 'r049_t21_ordinary_prepare_v11.py'
if not SOURCE.is_file():
    SOURCE = HERE.parent / 'source' / 'r049_t21_ordinary_prepare_v11.py'
ACTUAL_B102_TWO_DECODE = Path(
    '/data2/_shared/runs/ft_rounds/E2-R049a/L1/two_decode.json'
)


def load_runner():
    spec = importlib.util.spec_from_file_location('r049_t21_v11_schema', SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def v9_document():
    return {
        'schema': 'ft_r049_ordinary_two_decode/v9',
        'pause_enabled': False,
        'ft_dev_ack': False,
        'simultaneous_barrier': True,
        'overlap_basis': 'network_first_nonempty_and_terminal_only',
        'records': [
            {'response': {'content_text': 'left', 'reasoning_text': '', 'tool_calls': []},
             'completion_tokens': 512, 'ttft_s': 1.0, 'decode_tps': 30.0},
            {'response': {'content_text': 'right', 'reasoning_text': '', 'tool_calls': []},
             'completion_tokens': 512, 'ttft_s': 1.1, 'decode_tps': 31.0},
        ],
    }


def test_v10_consumes_the_v9_two_decode_producer_contract(tmp_path):
    runner = load_runner()
    path = tmp_path / 'two_decode.json'
    path.write_text(json.dumps(v9_document()), encoding='utf-8')

    assert len(runner._workload_rows(json.loads(path.read_text()))) == 2
    assert runner._output_tokens({'two_decode_diff512': path}) == 1024
    timing = runner._timing_from_document(path, 'two_decode_diff512')
    assert timing['samples'] == 2
    assert timing['completion_tokens'] == 1024


@pytest.mark.parametrize('field, value', [
    ('pause_enabled', True),
    ('ft_dev_ack', True),
    ('simultaneous_barrier', False),
    ('overlap_basis', 'unobserved'),
])
def test_v10_rejects_a_v9_document_without_ordinary_transport_evidence(field, value):
    runner = load_runner()
    document = v9_document()
    document[field] = value

    with pytest.raises(RuntimeError, match='transport contract differs'):
        runner._workload_rows(document)


@pytest.mark.skipif(not ACTUAL_B102_TWO_DECODE.is_file(),
                    reason='actual b102 L1 receipt is available only on the Linux stage host')
def test_linux_stage_consumes_actual_b102_l1_v9_two_decode_receipt():
    runner = load_runner()
    document = json.loads(ACTUAL_B102_TWO_DECODE.read_text(encoding='utf-8'))

    rows = runner._workload_rows(document)
    assert document['schema'] == 'ft_r049_ordinary_two_decode/v9'
    assert len(rows) == 2
    assert all(row['completion_tokens'] == 512 for row in rows)
    assert all(row['finish_reason'] == 'length' for row in rows)
    assert runner._full_text_sha256(document)

@pytest.mark.skipif(not (Path('/data2/_shared/runs/ft_rounds/E2-R049a/round.json').is_file() and ACTUAL_B102_TWO_DECODE.is_file()),
                    reason='sealed actual b102 closure is available only on the Linux stage host')
def test_linux_stage_b102_d04_and_independent_review_require_a_fresh_full_nine():
    runner = load_runner()
    closure = runner.require_r049a_failure_closure()
    assert closure['accepted_full_groups'] == 0
    assert closure['complete_L1_retained'] is False
    assert closure['fresh_full_nine_required'] is True
    assert closure['independent_review_sha256'] == 'e8759ebd95d6a444b37c553271e01a2029fe84c1881be3d9f99710da48a81e1a'

@pytest.mark.skipif(not (Path('/data2/_shared/runs/ft_rounds/E2-R049a/round.json').is_file() and ACTUAL_B102_TWO_DECODE.is_file()),
                    reason='sealed actual b102 closure is available only on the Linux stage host')
def test_linux_stage_b102_d04_and_independent_review_require_a_fresh_full_nine():
    runner = load_runner()
    closure = runner.require_r049a_failure_closure()
    assert closure['accepted_full_groups'] == 0
    assert closure['complete_L1_retained'] is False
    assert closure['fresh_full_nine_required'] is True
    assert closure['independent_review_sha256'] == 'e8759ebd95d6a444b37c553271e01a2029fe84c1881be3d9f99710da48a81e1a'

@pytest.mark.skipif(not (Path('/data2/_shared/runs/ft_rounds/E2-R049a/round.json').is_file() and ACTUAL_B102_TWO_DECODE.is_file()),
                    reason='sealed actual b102 closure is available only on the Linux stage host')
def test_linux_stage_b102_d04_and_independent_review_require_a_fresh_full_nine():
    runner = load_runner()
    closure = runner.require_r049a_failure_closure()
    assert closure['accepted_full_groups'] == 0
    assert closure['complete_L1_retained'] is False
    assert closure['fresh_full_nine_required'] is True
    assert closure['independent_review_sha256'] == 'e8759ebd95d6a444b37c553271e01a2029fe84c1881be3d9f99710da48a81e1a'
