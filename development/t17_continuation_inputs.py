"""Build all continuation lengths from actual target-tokenizer trace prefixes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

CANDIDATE = 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'
BOUNDARIES = (8192, 12416, 12736, 18944)
TAILS = (65, 4095, 4096, 4097, 8191, 8192, 8193)


def token_sha(ids):
    return hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()


def expand(prefixes, suffix):
    if prefixes.get('candidate_commit') != CANDIDATE or len(prefixes.get('cases', [])) != 4:
        raise ValueError('actual candidate and four target trace prefixes required')
    if not isinstance(suffix, list) or len(suffix) < max(TAILS)-1 or any(type(x) is not int for x in suffix):
        raise ValueError('actual target-tokenizer suffix must cover 8193-tail')
    by_length = {row['length']: row for row in prefixes['cases']}
    if set(by_length) != set(BOUNDARIES):
        raise ValueError('exact boundary matrix required')
    cases = []
    for length in BOUNDARIES:
        row = by_length[length]
        donor = row['donor']
        if (not isinstance(donor, list) or len(donor) != length+1 or any(type(x) is not int for x in donor)
                or donor[length-2:length] != row['expected_ngram']):
            raise ValueError('physical donor prefix/context differs')
        for tail in TAILS:
            query = donor + suffix[:tail-1]
            cases.append({'name':f'prefix-{length}-tail-{tail}', 'length':length, 'tail':tail,
                          'trace_index':row['trace_index'], 'messages_sha':row['messages_sha'],
                          'original_ids_sha256':row['original_ids_sha256'],
                          'expected_ngram':row['expected_ngram'], 'donor':donor, 'query':query,
                          'donor_input_ids_sha256':token_sha(donor), 'input_ids_sha256':token_sha(query)})
    return {'schema':'ft_t17_continuation_inputs/v1', 'candidate_commit':CANDIDATE,
            'trace_sha256':prefixes['trace_sha256'], 'cases':cases,
            'query_design':'actual trace L+1 prefix followed by target-tokenizer Y suffix; constructed inputs',
            'target_suffix_sha256':token_sha(suffix), 'target_suffix_tokens':len(suffix)}


def build():
    import t17_d14_gpu as gpu
    gpu.WT = Path('/data2/FreeToken/wt/e2d14-schedule')
    gpu.helper.CANDIDATE = CANDIDATE
    prefixes = gpu.build_inputs()
    from freetoken.utils import load_tokenizer
    import torch
    tokenizer = load_tokenizer(str(gpu.ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'))
    result = expand(prefixes, tokenizer.encode(' Y'*9000, add_special_tokens=False))
    if torch.cuda.is_initialized():
        raise ValueError('input CPU builder unexpectedly initialized CUDA')
    result['gpu_started'] = False
    result['requests_sent'] = False
    return result


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
