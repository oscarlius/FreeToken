"""Explicitly enabled deployment smoke; reuses R066 official SDK collection.

No service is launched here. Do not set RELEASE_SMOKE_BASE before deployment
approval. Historical running/graph=4 hashes are observations, not this baseline.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unicodedata

import pytest

HERE = Path(__file__).resolve().parent


class SmokeInvalid(RuntimeError):
    """Foreign prefill invalidates the probe; restart and repeat, no rollback."""


def required_environment(parent=None):
    source = os.environ if parent is None else parent
    names = ('RELEASE_SMOKE_BASE', 'RELEASE_SMOKE_MODE', 'RELEASE_SMOKE_RUN_DIR',
             'RELEASE_SMOKE_SERVE_LOG', 'RELEASE_SMOKE_OWNER', 'RELEASE_SMOKE_EXCLUSIVE_APPROVAL')
    missing = [name for name in names if not source.get(name)]
    if missing:
        raise ValueError('Explicit smoke requires variables: ' + ', '.join(missing))
    return {name: source[name] for name in names}


def validate_health(status_code, payload):
    assert status_code == 200
    assert payload.get('status') == 'ok' and payload.get('maintenance') == 'serving'


def validate_cold_rows(rows, expected_prompt, chunk):
    # Row count is not fixed: special-token anchors cap a chunk at the last anchor's
    # page boundary (8257 -> 512 + 7745) and layer-major admits the remainder whole,
    # so the count depends on prompt content. `chunk` is kept only for the call
    # signature. Only the token total, single-sequence rows and zero cache hits
    # identify one cold request. SmokeInvalid allows one restart per candidate
    # (handbook); a second one is treated as a failure and rolls back.
    if (any(row['new_sequences'] != 1 for row in rows)
            or sum(row['new_tokens'] for row in rows) > expected_prompt):
        raise SmokeInvalid('External prefill observed; restart current version and repeat smoke')
    assert rows
    assert all(row['cached_tokens'] == 0 for row in rows)
    assert sum(row['new_tokens'] for row in rows) == expected_prompt


def compare_with_baseline(results, prior):
    # Same prompt and config must reproduce the same prefill structure; compare it
    # before SHA so a structural change is reported as such, not as a text mismatch.
    for key, current in results.items():
        assert 'backend_cache_rows' in prior[key], 'baseline predates row-structure recording'
        assert current['backend_cache_rows'] == prior[key]['backend_cache_rows']
        assert current['sha256'] == prior[key]['sha256'] and current['usage'] == prior[key]['usage']


def compare_expected_reference(payload):
    expected = json.loads((HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json').read_text())
    assert all(expected[key] == payload[key] for key in ('mode', 'window', 'chunk', 'running', 'graph'))
    compare_with_baseline(payload['results'], expected['results'])


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_projection(record, expected_prompt):
    projection = record['projection']
    assert projection['finish_reason'] == 'length'
    assert projection['usage'] == {'prompt_tokens': expected_prompt,
        'completion_tokens': 128, 'total_tokens': expected_prompt + 128}
    text = projection['text']
    assert text and '\ufffd' not in text
    assert not any(unicodedata.category(c) == 'Cs' or
        (unicodedata.category(c) == 'Cc' and c not in '\n\r\t') for c in text)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def validate_owner(owner, mode, base, log, exclusive_approval):
    from release_config import HOST, MODES, serve_argv
    assert owner['mode'] == mode and owner['commit'] == MODES[mode][1]
    assert owner['argv'] == serve_argv(mode) and owner['host'] == HOST
    assert owner['log'] == str(log) and base == 'http://' + HOST + ':8095'
    assert exclusive_approval == owner['approval_id']


def test_release_smoke():
    required_environment()  # no opt-out: explicit invocation without config fails
    import httpx
    from release_config import MODEL, MODES
    mode = os.environ['RELEASE_SMOKE_MODE']
    base = os.environ['RELEASE_SMOKE_BASE'].rstrip('/')
    out = Path(os.environ['RELEASE_SMOKE_RUN_DIR'])
    out.mkdir(exist_ok=False)
    log = Path(os.environ['RELEASE_SMOKE_SERVE_LOG'])
    owner_path = Path(os.environ['RELEASE_SMOKE_OWNER'])
    from release_control import ACTIVE, helpers, verify_identity
    assert owner_path == ACTIVE
    owner_bytes = owner_path.read_bytes()
    owner = json.loads(owner_bytes)
    validate_owner(owner, mode, base, log, os.environ['RELEASE_SMOKE_EXCLUSIVE_APPROVAL'])
    d07 = helpers()
    verify_identity(d07, owner['supervisor'])
    verify_identity(d07, owner['service'])
    r066 = load(HERE.parent / 'r066_d16_discriminate_v2/sdk_adapter.py', 'release_r066')
    cache = load(HERE.parent / 'r066b_canary_v2/sdk_adapter.py', 'release_r066_cache')
    # Production must remain closed to callers until these first requests finish.
    if cache.cached_rows(log.read_text(encoding='utf-8')):
        (out / 'smoke_invalid.json').write_text(json.dumps({'classification': 'smoke_invalid',
            'reason': 'Prefill predates exclusive cold-smoke boundary', 'rollback': False}) + '\n')
        raise SmokeInvalid('Prior prefill; restart same version for cold smoke')
    offset = log.stat().st_size
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.get(base + '/health')
        validate_health(response.status_code, response.json())
        (out / 'health.json').write_text(json.dumps({'status': response.status_code,
            'body': response.text}, indent=2) + '\n')
    results = {}
    for key in ('short', 'long'):
        item = r066.inputs()[key]
        with log.open('rb') as handle:
            handle.seek(offset)
            gap = handle.read()
        if cache.cached_rows(gap.decode('utf-8', errors='strict')):
            (out / 'smoke_invalid.json').write_text(json.dumps({'classification': 'smoke_invalid',
                'reason': 'External prefill between smoke requests', 'rollback': False}) + '\n')
            raise SmokeInvalid('External prefill between smoke requests')
        offset += len(gap)
        record = r066.collect_one(base, MODEL, key, item, out)
        with log.open('rb') as handle:
            handle.seek(offset)
            window = handle.read()
        (out / (key + '.serve-window.txt')).write_bytes(window)
        rows = cache.cached_rows(window.decode('utf-8', errors='strict'))
        try:
            validate_cold_rows(rows, item['prompt_tokens'], MODES[mode][3])
        except SmokeInvalid as exc:
            (out / 'smoke_invalid.json').write_text(json.dumps({'classification': 'smoke_invalid',
                'reason': str(exc), 'rollback': False}) + '\n')
            raise
        assert record['cached_tokens_observation']['value'] in (None, 0)
        results[key] = {'sha256': valid_projection(record, item['prompt_tokens']),
            'usage': record['projection']['usage'],
            'finish_reason': record['projection']['finish_reason'],
            'api_cached_tokens': record['cached_tokens_observation']['value'],
            'backend_cache_rows': rows, 'service_log_start_byte': offset}
        offset += len(window)
    payload = {'schema': 'ft_release_cold_smoke/v1', 'results': results,
        'mode': mode, 'window': MODES[mode][2], 'chunk': MODES[mode][3],
        'running': 2, 'graph': 2, 'owner_sha256': hashlib.sha256(owner_bytes).hexdigest(),
        'actual_supervisor_argv': owner['argv'],
        'exclusive_maintenance_approval': owner['approval_id'],
        'historical_private_graph4_SHA_not_used_as_gate': True}
    # Retain actual baseline before an optional restore comparison can fail.
    (out / 'cold_baseline.json').write_text(json.dumps(payload, indent=2) + '\n')
    assert owner_path.read_bytes() == owner_bytes
    verify_identity(d07, owner['service'])
    if mode == 'release':
        compare_expected_reference(payload)
    baseline = os.getenv('RELEASE_SMOKE_BASELINE')
    if baseline:
        prior_payload = json.loads(Path(baseline).read_text())
        assert all(prior_payload[k] == payload[k] for k in ('mode', 'window', 'chunk', 'running', 'graph'))
        compare_with_baseline(results, prior_payload['results'])
