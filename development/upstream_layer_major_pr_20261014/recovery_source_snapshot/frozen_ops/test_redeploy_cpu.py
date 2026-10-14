"""Exercise the actual retry entry point without HTTP, service startup or GPU."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import release_config as config
import run_smoke
import test_smoke_live as smoke
from smoke_campaign import attempt


def owner(root, name):
    run = root / name
    run.mkdir(exist_ok=True)
    return {'mode': 'release', 'commit': config.MODES['release'][1],
            'approval_id': name, 'run_dir': str(run), 'log': str(run / 'serve.log'),
            'host': config.HOST, 'argv': config.serve_argv('release')}


def test_actual_entry_second_invalid_is_failure_and_third_blocked(tmp_path, monkeypatch):
    # e3：run_smoke 的参考值路径已改为 release_e3_reference_20261012；这里用 e2 参考值副本作固定夹具。
    reference = json.loads((smoke.HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json').read_text())
    (tmp_path / 'release_e3_reference_20261012').mkdir()
    (tmp_path / 'release_e3_reference_20261012' / 'expected_reference.json').write_text(json.dumps(reference))
    monkeypatch.setattr(run_smoke, 'HERE', tmp_path / 'ops')
    root = tmp_path / 'runs/production'
    root.mkdir(parents=True)
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    campaign = root / 'DEPLOY-CPU'
    for index, name in enumerate(('DEPLOY-CPU', 'DEPLOY-CPU-retry1')):
        current = owner(root, name)
        run = Path(current['run_dir'])
        active = tmp_path / 'active.json'
        active.write_text(json.dumps(current))
        for key, value in {'BASE': 'http://' + config.HOST + ':8095', 'MODE': 'release',
                           'OWNER': str(active), 'SERVE_LOG': current['log'],
                           'RUN_DIR': str(run / 'smoke_first'), 'EXCLUSIVE_APPROVAL': name,
                           'CAMPAIGN_DIR': str(campaign)}.items():
            monkeypatch.setenv('RELEASE_SMOKE_' + key, value)

        def invalid(*args, **kwargs):
            out = run / 'smoke_first'
            out.mkdir()
            (out / 'smoke_invalid.json').write_text('{}')
            return SimpleNamespace(returncode=1, stdout='1 failed\n')

        monkeypatch.setattr(run_smoke.subprocess, 'run', invalid)
        assert run_smoke.main() == (75 if index == 0 else 1)
    state = json.loads((campaign / 'smoke_campaign.json').read_text())
    assert [a['outcome'] for a in state['attempts']] == ['smoke_invalid', 'failed_second_smoke_invalid']
    with pytest.raises(RuntimeError, match='only one retry'):
        with attempt(campaign, root, owner(root, 'DEPLOY-CPU-retry2'), state['reference_sha256']):
            pytest.fail('Third SDK attempt must never run')


def test_failed_or_unfinished_campaign_never_retries(tmp_path):
    first = owner(tmp_path, 'CAMPAIGN')
    campaign = Path(first['run_dir'])
    with pytest.raises(RuntimeError, match='CPU simulated crash'):
        with attempt(campaign, tmp_path, first, 'reference'):
            raise RuntimeError('CPU simulated crash')
    with pytest.raises(RuntimeError, match='only one retry'):
        with attempt(campaign, tmp_path, owner(tmp_path, 'CAMPAIGN-retry1'), 'reference'):
            pytest.fail('Failure cannot become invalid retry')


def test_campaign_binds_reference_generation_and_exclusive_lock(tmp_path):
    first = owner(tmp_path, 'CAMPAIGN')
    campaign = Path(first['run_dir'])
    with attempt(campaign, tmp_path, first, 'reference') as state:
        with pytest.raises(FileExistsError):
            with attempt(campaign, tmp_path, first, 'reference'):
                pytest.fail('Concurrent attempt must not run')
        state['outcome'] = 'smoke_invalid'
    retry = owner(tmp_path, 'CAMPAIGN-retry1')
    with pytest.raises(ValueError, match='reference changed'):
        with attempt(campaign, tmp_path, retry, 'different'):
            pytest.fail('Changed reference must not run')
    with pytest.raises(ValueError, match='generation'):
        with attempt(campaign, tmp_path, first, 'reference'):
            pytest.fail('Same service must not be retried')
    with attempt(campaign, tmp_path, retry, 'reference') as state:
        state['outcome'] = 'passed'


@pytest.mark.parametrize('field', ['structure', 'sha', 'usage', 'window'])
def test_initial_reference_enforced_without_optional_baseline(monkeypatch, tmp_path, field):
    monkeypatch.delenv('RELEASE_SMOKE_BASELINE', raising=False)
    # e3：参考值路径已改为 release_e3_reference_20261012；这里用 e2 参考值副本作固定夹具，检验同一套强制比较。
    reference = json.loads((smoke.HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json').read_text())
    (tmp_path / 'release_e3_reference_20261012').mkdir()
    (tmp_path / 'release_e3_reference_20261012' / 'expected_reference.json').write_text(json.dumps(reference))
    monkeypatch.setattr(smoke, 'HERE', tmp_path / 'ops')
    smoke.compare_expected_reference(reference)
    changed = copy.deepcopy(reference)
    if field == 'structure':
        changed['results']['long']['backend_cache_rows'] = [{'new_sequences': 1, 'new_tokens': 8257, 'cached_tokens': 0}]
    elif field == 'sha':
        changed['results']['long']['sha256'] = '0' * 64
    elif field == 'usage':
        changed['results']['long']['usage']['completion_tokens'] = 127
    else:
        changed['window'] = 49152
    with pytest.raises(AssertionError):
        smoke.compare_expected_reference(changed)
