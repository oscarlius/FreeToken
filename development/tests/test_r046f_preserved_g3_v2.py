"""Retry only unfinished scopes and bind accepted G3 without reopening raw data."""
import importlib.util
import json
from pathlib import Path

import pytest

DEV = Path(__file__).parents[1]


def load():
    spec = importlib.util.spec_from_file_location('r046f_preserved', DEV / 'r046f_d07_t06_prepare_v2.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def accepted_fixture(tmp_path, monkeypatch):
    m = load()
    run = tmp_path / 'E2-R046e'
    meta = run / 'metadata'
    meta.mkdir(parents=True)
    doc = {'completed_arms': ['G3-off', 'G3-on'], 'base': {'commit': m.CANDIDATE},
           'serve': {'window': 98304, 'memory_ratio': .88, 'G3_pause': False}}
    (run / 'round.json').write_text(json.dumps(doc))
    (run / 'MANIFEST.sha256').write_text('metadata-only fixture\n')
    review = {'rid': 'E2-R046e', 'verdict': 'failed_harness', 'candidate_commit': m.CANDIDATE,
              'g3_recomputation': {'full_text_equal': True, 'd0_h2d_d2d_equal': True,
                 'record_contract_equal': {'completion_tokens': True},
                 'arms': [{'arm': name, 'route_directory_exists': trace, 'text_sha256': 'a'*64,
                           'record': {'prompt_tokens': 32064, 'completion_tokens': 128, 'finish_reason': 'length'}}
                          for name, trace in [('g3_off', False), ('g3_on', True)]]}}
    p = meta / 'independent_failed_review.json'
    p.write_text(json.dumps(review))
    p.chmod(0o444)
    monkeypatch.setattr(m, 'PRESERVED_G3_REVIEW_SHA256', m.sha(p))
    class D:
        def require_closed_round(self, rid, verdict):
            assert (rid, verdict) == ('E2-R046e', 'failed_harness')
            return run
    return m, D(), run, doc


def test_reuse_only_reads_sealed_metadata_not_original_measurements(tmp_path, monkeypatch):
    m, d, run, _ = accepted_fixture(tmp_path, monkeypatch)
    real_read = Path.read_bytes
    def metadata_read(p):
        assert 'g3g4' not in p.parts
        return real_read(p)
    monkeypatch.setattr(Path, 'read_bytes', metadata_read)
    value = m.require_preserved_g3(d)
    assert value['reused_g3']['GPU_rerun'] is False
    assert value['g3']['byte_identical'] is True
    assert value['reused_g3']['round_sha256'] == m.sha(run / 'round.json')


@pytest.mark.parametrize('key,value', [('window', 73728), ('memory_ratio', .80), ('G3_pause', True)])
def test_changed_configuration_cannot_reuse_accepted_pair(tmp_path, monkeypatch, key, value):
    m, d, run, doc = accepted_fixture(tmp_path, monkeypatch)
    doc['serve'][key] = value
    (run / 'round.json').write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match='closure/configuration'):
        m.require_preserved_g3(d)


def test_changed_review_bytes_cannot_reuse_pair(tmp_path, monkeypatch):
    m, d, run, _ = accepted_fixture(tmp_path, monkeypatch)
    p = run / 'metadata/independent_failed_review.json'
    p.chmod(0o600)
    p.write_text('{}')
    p.chmod(0o444)
    with pytest.raises(RuntimeError, match='closure/configuration'):
        m.require_preserved_g3(d)


def test_real_file_dry_has_only_remaining_four_services(tmp_path, monkeypatch):
    m = load()
    # Reuse the existing actual FILEdry regression and verify its resulting service set.
    import importlib.util
    spec = importlib.util.spec_from_file_location('existing_filedry', DEV / 'tests/test_r046f_d07_t06_prepare_v2.py')
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    tests.test_file_dry_run_never_starts_service_or_allocates_batch(monkeypatch, tmp_path)
    receipt = json.loads((tmp_path / 'rounds/.filedry_E2-R046f/dry_run_receipt.json').read_text())
    assert [arm['name'] for arm in receipt['services']] == ['G_seed12k', 'G_seed_45k', 'G_seed_real', 'G_two']
    assert receipt['service_started'] is False
    assert not any('g3_' in arm['name'] for arm in receipt['services'])
