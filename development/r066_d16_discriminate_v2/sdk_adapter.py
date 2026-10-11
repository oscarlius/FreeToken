"""R066 thin criteria adapter over the hash-bound R065 official SDK collector."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R065 = HERE.parent / 'r065_d16_discriminate_v1'
R065_ADAPTER_SHA = '7870d1adab240ea1b0ee05e8035b13d77cd9b414597405a1987d60fea68412cd'
R065_INPUTS_SHA = '18cce7cde13420f793cffd55ff8ce6e542f99b21bb193038912421854156539e'
B_BODY_SHA = '9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c'
D_BODY_SHA = 'ddb0e282943654ab3d6a72d83d55276ab66c7377e7d138127df48246032bc4e9'

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

if _sha(R065 / 'sdk_adapter.py') != R065_ADAPTER_SHA or _sha(R065 / 'inputs.json') != R065_INPUTS_SHA:
    raise RuntimeError('R065 reusable SDK/input source differs')
_spec = importlib.util.spec_from_file_location('r066_hash_bound_r065_sdk', R065 / 'sdk_adapter.py')
r065 = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(r065)

CriterionMismatch = r065.CriterionMismatch
write = r065.write
collect_one = r065.collect_one
pair = r065.pair
discriminate = r065.discriminate

def inputs():
    return json.loads((R065 / 'inputs.json').read_text(encoding='utf-8'))['items']

def body_sha(record):
    return hashlib.sha256(record['projection']['text'].encode('utf-8')).hexdigest()

def _result(run_dir, service, proposal):
    write(Path(run_dir) / 'criteria_result.json', {
        'schema': 'ft_r066_d16_criteria/v2', 'rid': 'E2-R066-d16-discriminate-v2',
        'service': service, **proposal,
    })

def run_service(base, model, service, run_dir, d_enabled=False):
    """Perform only B, C, or an explicitly admitted D service; no launch logic."""
    item = inputs()
    output = Path(run_dir) / service / 'calls'
    output.mkdir()
    try:
        if service == 'B':
            record = collect_one(base, model, 'B1', item['long'], output)
            if body_sha(record) != B_BODY_SHA:
                raise CriterionMismatch('B body SHA differs')
            write(output / 'cached_tokens_observation.json', record['cached_tokens_observation'])
            write(output / 'service_result.json', {'service': service, 'passed': True, 'calls': 1})
            return record
        if service == 'D':
            if not d_enabled:
                raise RuntimeError('D scheduling expression is not evidenced')
            record = collect_one(base, model, 'D1', item['long'], output)
            if body_sha(record) != D_BODY_SHA:
                raise CriterionMismatch('D body SHA differs')
            write(output / 'service_result.json', {'service': service, 'passed': True, 'calls': 1})
            return record
        if service != 'C':
            raise ValueError('unapproved service')
        b = json.loads((Path(run_dir) / 'B' / 'calls' / 'B1.json').read_text(encoding='utf-8'))
        long_record, _ = pair(base, model, [('C_long', item['long']), ('C_short', item['short'])], output)
        r065.comparable(b, long_record, ('finish_reason', 'usage'))
        records = pair(base, model, [('C_alpha', item['alpha']), ('C_beta', item['beta'])], output)
        for record, key, other in zip(records, ('alpha', 'beta'), ('beta', 'alpha')):
            discriminate(record['projection']['text'], item[key]['marker'], item[other]['marker'])
        proposal = {
            'proposed_verdict': 'passed_R066_criteria', 'handoff_ready': True,
            'scope': {'services': 3 if d_enabled else 2, 'calls': 6 if d_enabled else 5},
            'c_long_body_matches_B_observation': body_sha(long_record) == B_BODY_SHA,
            'cached_tokens_policy': 'observation_only_missing_is_not_zero',
            'd_status': 'passed' if d_enabled else 'skipped_no_evidenced_8256_plus_1_expression',
        }
        write(output / 'service_result.json', {'service': service, 'passed': True, 'calls': 4})
        _result(run_dir, service, proposal)
        return records
    except BaseException as exc:
        result = Path(run_dir) / 'criteria_result.json'
        if not result.exists():
            _result(run_dir, service, {
                'proposed_verdict': 'not_met' if isinstance(exc, CriterionMismatch) else 'failed_harness',
                'handoff_ready': False, 'reason': str(exc), 'exception_type': type(exc).__name__,
            })
        raise
