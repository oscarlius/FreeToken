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


@pytest.mark.skipif(not os.getenv('RELEASE_SMOKE_BASE'), reason='deployment not approved/enabled')
def test_release_smoke():
    import httpx
    from release_config import MODEL, MODES
    mode = os.getenv('RELEASE_SMOKE_MODE', 'release')
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
    assert not cache.cached_rows(log.read_text(encoding='utf-8'))
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.get(base + '/health')
        assert response.status_code == 200
        (out / 'health.json').write_text(json.dumps({'status': response.status_code,
            'body': response.text}, indent=2) + '\n')
    results = {}
    for key in ('short', 'long'):
        item = r066.inputs()[key]
        offset = log.stat().st_size
        record = r066.collect_one(base, MODEL, key, item, out)
        with log.open('rb') as handle:
            handle.seek(offset)
            window = handle.read()
        (out / (key + '.serve-window.txt')).write_bytes(window)
        rows = cache.cached_rows(window.decode('utf-8', errors='strict'))
        chunk = MODES[mode][3]
        expected_rows = (item['prompt_tokens'] + chunk - 1) // chunk
        assert len(rows) == expected_rows and all(row['cached_tokens'] == 0 for row in rows)
        assert sum(row['new_tokens'] for row in rows) == item['prompt_tokens']
        assert record['cached_tokens_observation']['value'] in (None, 0)
        results[key] = {'sha256': valid_projection(record, item['prompt_tokens']),
            'usage': record['projection']['usage'],
            'finish_reason': record['projection']['finish_reason'],
            'api_cached_tokens': record['cached_tokens_observation']['value'],
            'backend_cache_rows': rows, 'service_log_start_byte': offset}
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
    baseline = os.getenv('RELEASE_SMOKE_BASELINE')
    if baseline:
        prior_payload = json.loads(Path(baseline).read_text())
        assert all(prior_payload[k] == payload[k] for k in ('mode', 'window', 'chunk', 'running', 'graph'))
        prior = prior_payload['results']
        assert all(results[key]['sha256'] == prior[key]['sha256'] and
                   results[key]['usage'] == prior[key]['usage'] for key in results)
