"""Derive T17 claims from raw endpoint receipts, scheduler observations and states."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct


# The 8192 context is deliberately supplied by the CPU trace replay receipt.
# Do not invent an adjacent-token context for a boundary which was not in the
# historical semantic proof.
CASES = (
    {'name': 'chunk-edge-8192', 'length': 8192, 'trace_index': None, 'context': None},
    {'name': 'inside-12416', 'length': 12416, 'trace_index': 11, 'context': [1469, 17]},
    {'name': 'aligned-12736', 'length': 12736, 'trace_index': 10, 'context': [198, 248068]},
    {'name': 'inside-18944', 'length': 18944, 'trace_index': 5, 'context': [11, 4093]},
)
ROLES = ('conv_states', 'recurrent_states', 'slot:ple_conv', 'slot:ple_ngram_ctx')
SHORT_TAIL = 65
LONG_TAILS = (4097, 4161, 5001)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ids_sha(ids):
    return hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line]


def one(rows, description):
    if len(rows) != 1:
        raise ValueError(f'{description}: expected one observed record, got {len(rows)}')
    return rows[0]


def resolve_case(case, cpu_contexts):
    """Bind a case to the CPU replay's exact pre-boundary token pair."""
    result = dict(case)
    if result['context'] is None:
        context = cpu_contexts.get(result['length'], cpu_contexts.get(str(result['length'])))
        if not (isinstance(context, list) and len(context) == 2 and all(isinstance(x, int) for x in context)):
            raise ValueError('CPU replay did not supply the two-token boundary context')
        result['context'] = context
    return result


def _receipt(arm, request):
    raw = json.loads((arm / f'{request}.json').read_text(encoding='utf-8'))
    required = {'payload', 'response', 'status', 'response_sha256',
                'expected_input_ids_sha256', 'observation_range', 'raw_response_file'}
    missing = required.difference(raw)
    if missing:
        raise ValueError('endpoint receipt missing fields: ' + ', '.join(sorted(missing)))
    raw_response = arm / raw['raw_response_file']
    response_path = raw_response.resolve(strict=True)
    if (raw_response.is_symlink() or arm.resolve() not in response_path.parents
            or not response_path.is_file() or sha(response_path) != raw['response_sha256']):
        raise ValueError('endpoint response bytes do not match their receipt hash')
    if raw['status'] != 200 or not isinstance(raw['response'], dict):
        raise ValueError('endpoint did not return the recorded successful response')
    response = raw['response']
    if json.loads(response_path.read_bytes()) != response:
        raise ValueError('parsed endpoint response does not match its raw response bytes')
    expected = {'uid', 'text', 'finished', 'finish_reason', 'usage', 'input_ids_sha256'}
    if expected.difference(response):
        raise ValueError('endpoint response is missing required actual-output fields')
    return raw, response


def request_evidence(arm, request, expected_cached, maximum):
    """Bind a serial HTTP request to its scheduler UID, exact IDs and token stream."""
    raw, response = _receipt(arm, request)
    if raw['payload'].get('max_tokens') != maximum:
        raise ValueError('request did not use the required output limit')
    rows = jsonl(arm / 'observations.jsonl')
    markers = raw['observation_range']
    selected = rows[markers['start']:markers['end']]
    incoming = one([r for r in selected if r['kind'] == 'input'], request + ' input')
    uid = incoming['uid']
    if str(response['uid']) != uid or any(r.get('uid') != uid for r in selected):
        raise ValueError('serial request observation contains another UID')
    if any(r['kind'] == 'error' for r in selected):
        raise ValueError('actual scheduler error in request')
    ids = incoming['input_ids']
    actual_sha = ids_sha(ids)
    if (incoming['input_length'] != len(ids) or incoming['ids_int32le_sha256'] != actual_sha
            or raw['expected_input_ids_sha256'] != actual_sha or response['input_ids_sha256'] != actual_sha):
        raise ValueError('actual tokenizer input hash differs')
    if raw['payload'].get('input_ids') != ids:
        raise ValueError('submitted exact-ID payload differs from actual tokenizer input')
    sampling = incoming.get('sampling', {})
    if sampling.get('temperature') != 0.0 or sampling.get('max_tokens') != maximum:
        raise ValueError('actual tokenizer sampling differs from the temperature-zero request')
    admitted = one([r for r in selected if r['kind'] == 'admitted'], request + ' admission')
    usage = response['usage']
    if (admitted['prompt_tokens'] != len(ids) or usage['prompt_tokens'] != len(ids)
            or admitted['cached_tokens'] != expected_cached or usage['cached_tokens'] != expected_cached):
        raise ValueError('actual cache admission differs from the exact planned boundary')
    tokens = [r for r in selected if r['kind'] == 'token']
    if (not tokens or len(tokens) > maximum or usage['completion_tokens'] != len(tokens)
            or [r['token'] for r in tokens] != [int(r['token']) for r in tokens]
            or sum(r['finished'] is True for r in tokens) != 1 or tokens[-1]['finished'] is not True
            or response['finished'] is not True):
        raise ValueError('actual sampled token stream is missing a unique terminal result')
    forwards = [r for r in selected if r['kind'] == 'prefill']
    if not forwards or forwards[0]['cached_tokens'] != expected_cached:
        raise ValueError('executed input and actual cache admission disagree')
    return {'uid': uid, 'input_ids': ids, 'input_sha256': actual_sha,
            'actual_cached_tokens': admitted['cached_tokens'],
            'tokens': [r['token'] for r in tokens], 'forwards': forwards,
            'observations': selected, 'response': response,
            'sampled_token_ids': [r['token'] for r in tokens], 'raw_text': response['text'],
            'response_sha256': raw['response_sha256'],
            'observation_sha256': sha(arm / 'observations.jsonl')}


def load_tensor(path):
    import torch
    return torch.load(path, map_location='cpu', weights_only=True)


def bit_equal(left, right):
    import torch
    if left.shape != right.shape or left.dtype != right.dtype:
        return False

    def wire(tensor):
        # Singleton slices may count as contiguous while retaining stride > 1.
        # A fresh flat allocation guarantees the unit stride dtype.view needs.
        flat = torch.empty(tensor.numel(), dtype=tensor.dtype, device=tensor.device)
        flat.copy_(tensor.reshape(-1))
        return flat.view(torch.uint8)

    return torch.equal(wire(left), wire(right))


def state_file(state_root, record, role, read):
    name = record.get('files', {}).get(role)
    if not isinstance(name, str):
        raise ValueError('missing serialized state role: ' + role)
    raw = state_root / name
    path = raw.resolve(strict=True)
    if raw.is_symlink() or state_root.resolve() not in path.parents or not path.is_file():
        raise ValueError('state file escapes the observed dump')
    return read(path), {'file': name, 'sha256': sha(path)}


def _validate_states(case, state_root, donor, hit, *, read=load_tensor, equal=bit_equal):
    dumps = jsonl(state_root / 'index.jsonl')
    if any(row['kind'] in ('resume', 'archive') for row in dumps):
        raise ValueError('unexpected host-tier restore or archive in device-resume gate')
    length = case['length']
    donation = one([r for r in dumps if r['kind'] == 'donate'
                    and r['uid'] == donor['uid'] and r['length'] == length], 'donor state')
    resumed = one([r for r in dumps if r['kind'] == 'resume-device'
                   and r['uid'] == hit['uid'] and r['length'] == length], 'resumed state')
    restore = one([r for r in hit['observations'] if r['kind'] == 'restore-device'], 'D2D restore')
    note = json.loads(resumed['note'])
    if (restore['cached_tokens'] != length or donation['dev_slots'] != [restore['src']]
            or resumed['dev_slots'] != [restore['src'], restore['dst']]
            or note != {'src': restore['src'], 'dst': restore['dst']}
            or donation['seq'] >= resumed['seq']):
        raise ValueError('donation and restore source/destination slots do not bind')
    states = {}
    for role in ROLES:
        before, source = state_file(state_root, donation, role, read)
        after, target = state_file(state_root, resumed, role, read)
        if (before.shape[1] != 1 or after.shape[1] != 2
                or not equal(before[:, 0], after[:, 0])
                or not equal(after[:, 0], after[:, 1])):
            raise ValueError('D2D source/destination state is not bitwise equal: ' + role)
        states[role] = {'donor': source, 'resume': target, 'bitwise_equal': True}
        if role == 'slot:ple_ngram_ctx':
            states[role].update(observed_donor=before.flatten().tolist(),
                                observed_resume=after[:,1].flatten().tolist())
        if role == 'slot:ple_ngram_ctx' and before.flatten().tolist() != case['context']:
            raise ValueError('donor integer ngram state has the wrong token identities')
    return donation, resumed, restore, states


def validate_case(case, cold_arm, hot_arm, *, tail, state_root=None, cold_request='cold',
                  donor_request='donor', hit_request='hit', read=load_tensor, equal=bit_equal):
    """Validate one cold-vs-hit continuation tail (65 or a layer-major long tail)."""
    if tail != SHORT_TAIL and tail not in LONG_TAILS:
        raise ValueError('unsupported continuation tail')
    length = case['length']
    cold = request_evidence(cold_arm, cold_request, 0, 128)
    donor = request_evidence(hot_arm, donor_request, 0, 2)
    hit = request_evidence(hot_arm, hit_request, length, 128)
    expected_query_length = length + tail
    if (len(cold['input_ids']) != expected_query_length or cold['input_ids'] != hit['input_ids']
            or len(donor['input_ids']) != length + 1 or donor['input_ids'] != hit['input_ids'][:length + 1]):
        raise ValueError('cold/query IDs or L+1 donor IDs do not bind to the selected boundary')
    if len(donor['tokens']) != 2 or not any(
            row['kind'] == 'token' and row['finished'] and row['finish_reason'] == 'length'
            for row in donor['observations']):
        raise ValueError('donor did not produce the required two-token nonterminal donation')
    ids = hit['input_ids']
    if ids[length - 2:length] != case['context']:
        raise ValueError('observed prompt has the wrong absolute boundary context')
    if not any(row['layer_major'] for row in donor['forwards']):
        raise ValueError('donor never reached the layer-major generation path')
    children = [r for r in hit['observations'] if r['kind'] == 'layer-children']
    if tail == SHORT_TAIL:
        if children:
            raise ValueError('short continuation unexpectedly used layer-major children')
    else:
        child = one(children, 'layer-major child observation')
        if (child['outer_cached_tokens'] != length or not child['children']
                or child['children'][0]['cached_tokens'] != length
                or child['children'][0]['device_tokens'] <= length
                or child['children'][0]['has_initial_state'] is not True):
            raise ValueError('first layer-major child did not retain the resumed cached state')
    state_root = Path(state_root) if state_root is not None else hot_arm / 'state'
    donation, resumed, restore, states = _validate_states(case, state_root, donor, hit, read=read, equal=equal)
    same_tokens = cold['tokens'] == hit['tokens']
    cold_terminal = cold['tokens'] and cold['observations'][-1]['finish_reason']
    hit_terminal = hit['tokens'] and hit['observations'][-1]['finish_reason']
    same_text = (cold['response']['text'] == hit['response']['text']
                 and cold_terminal == hit_terminal)
    return {'name': case['name'], 'boundary': length, 'trace_index': case['trace_index'],
            'tail': tail, 'prompt_ids_sha256': hit['input_sha256'], 'actual_cached_tokens': hit['actual_cached_tokens'],
            'donor_uid': donor['uid'], 'hit_uid': hit['uid'], 'source_slot': restore['src'],
            'destination_slot': restore['dst'], 'donate_seq': donation['seq'],
            'resume_seq': resumed['seq'], 'expected_context': case['context'],
            'state_roles': states, 'cold_token_ids': cold['tokens'], 'hit_token_ids': hit['tokens'],
            'cold_token_ids_sha256': ids_sha(cold['tokens']), 'hit_token_ids_sha256': ids_sha(hit['tokens']),
            'tokens_bitwise_equal': same_tokens, 'full_text_equal': same_text,
            'cold_raw_text': cold['response']['text'], 'hit_raw_text': hit['response']['text'],
            'cold_endpoint_finish_reason': cold['response']['finish_reason'],
            'hit_endpoint_finish_reason': hit['response']['finish_reason'],
            'cold_scheduler_finish_reason': cold_terminal,
            'hit_scheduler_finish_reason': hit_terminal,
            'receipts': {'cold': cold['response_sha256'], 'donor': donor['response_sha256'],
                         'hit': hit['response_sha256']},
            'passed': same_tokens and same_text}


def validate_case_matrix(case, arms):
    """Require the short tail plus exactly one long layer-major continuation tail."""
    if SHORT_TAIL not in arms:
        raise ValueError('missing short continuation arm')
    long = [tail for tail in LONG_TAILS if tail in arms]
    if len(long) != 1:
        raise ValueError('require exactly one approved long continuation arm')
    results = []
    for tail in (SHORT_TAIL, long[0]):
        cold_arm, hot_arm = arms[tail]
        result = validate_case(case, cold_arm, hot_arm, tail=tail)
        if not result['passed']:
            raise ValueError('cold and hit generations differ')
        results.append(result)
    return {'case': case['name'], 'boundary': case['length'], 'tails': results, 'passed': True}
