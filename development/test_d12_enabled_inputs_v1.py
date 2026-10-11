import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('d12_inputs', Path(__file__).with_name('d12_enabled_inputs_v1.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_request_suffix_is_not_segment_coverage():
    rows = [
        {'round': 0, 'request_suffix_tokens': 512, 'segment_tokens': [512]},
        {'round': 1, 'request_suffix_tokens': 297, 'segment_tokens': [64, 233]},
        {'round': 2, 'request_suffix_tokens': 123, 'segment_tokens': [123]},
    ]
    report = mod.segment_statistics(rows)
    assert report['warm_requests'] == 2
    assert report['warm_request_suffix_le_256'] == 1
    assert report['warm_requests_with_any_segment_le_256'] == 2
    assert report['warm_segments_le_256'] == 3
    assert report['business_segment_boundary_counts']['64'] == 1
    assert report['business_segment_boundary_counts']['1'] == 0


def test_segment_total_must_equal_suffix():
    with pytest.raises(ValueError, match='totals'):
        mod.segment_statistics([{'round': 1, 'request_suffix_tokens': 297, 'segment_tokens': [64, 234]}])


def test_cold_missing_api_cache_uses_independently_bound_d0():
    binding = {'d0': {'cached_tokens': 0}, 'api': {'cached_tokens':
        {'independently_verified': False, 'state': 'missing', 'value': None}}}
    assert mod.verified_cached_tokens({'usage': {}}, binding, 0) == 0
    with pytest.raises(ValueError, match='only the independently bound cold'):
        mod.verified_cached_tokens({'usage': {}}, binding, 1)


def test_reported_cache_must_match_d0():
    binding = {'d0': {'cached_tokens': 12864}, 'api': {'cached_tokens':
        {'independently_verified': True, 'state': 'reported', 'value': 12864}}}
    with pytest.raises(ValueError, match='cache accounting'):
        mod.verified_cached_tokens({'usage': {'prompt_tokens_details': {'cached_tokens': 12800}}}, binding, 2)


@pytest.mark.parametrize('rel', ['../outside.json', '/absolute.json', 'a/../inside.json'])
def test_source_paths_cannot_escape(tmp_path, rel):
    reader = mod.SealedInputs.__new__(mod.SealedInputs)
    reader.root, reader.manifest, reader.reads = tmp_path, {}, {}
    with pytest.raises(ValueError, match='relative path'):
        reader.read(rel)


def test_source_sha_tampering_is_rejected(tmp_path):
    path = tmp_path / 'input.json'
    path.write_bytes(b'[1,2,4]')
    path.chmod(0o444)
    reader = mod.SealedInputs.__new__(mod.SealedInputs)
    reader.root, reader.reads = tmp_path, {}
    reader.manifest = {'input.json': hashlib.sha256(b'[1,2,3]').hexdigest()}
    with pytest.raises(ValueError, match='SHA differs'):
        reader.read('input.json')
