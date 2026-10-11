#!/usr/bin/env python3
"""Bind D12 replay inputs and distinguish request suffixes from MoE segments.

Offline derivation only. Reads sealed R046g evidence; never starts a service,
imports torch, obtains a GPU lock, or assigns a formal round number.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys

ROUND_SHA = '3f50a0ffb69e24e65eb10df1b925ed9bbf75c74e51ddd385f05369947134f54d'
MANIFEST_SHA = '282f1a046a33d46345c9b3f72630a2f0971c3d4f92839c2e0d6f100e6232c9f1'
GROUPS = {'G_seed12k': 12, 'G_seed_45k': 12, 'G_seed_real': 8}
THRESHOLD = 256


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SealedInputs:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ValueError('source root must be a physical directory')
        self.reads = {}
        manifest = self.read('MANIFEST.sha256', MANIFEST_SHA)
        self.manifest = {}
        for line in manifest.decode().splitlines():
            digest, rel = line.split('  ', 1)
            if rel in self.manifest or len(digest) != 64:
                raise ValueError('duplicate or malformed manifest entry')
            self.manifest[rel] = digest
        round_value = json.loads(self.read('round.json', ROUND_SHA))
        if round_value['round_id'] != 'E2-R046g' or round_value['verdict'] != 'measured':
            raise ValueError('source round identity/verdict differs')

    def relative(self, absolute):
        return Path(absolute).relative_to(self.root).as_posix()

    def read(self, rel, expected=None):
        posix = PurePosixPath(rel)
        if posix.is_absolute() or '..' in posix.parts or str(posix) != rel:
            raise ValueError('invalid source relative path')
        path = self.root.joinpath(*posix.parts)
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            raise ValueError('source file absent or traverses symlink')
        if sys.platform == 'linux' and path.stat().st_mode & 0o222:
            raise ValueError('source file is writable')
        raw = path.read_bytes()
        expected = expected or self.manifest.get(rel)
        if expected is None or sha(raw) != expected:
            raise ValueError('source SHA differs: ' + rel)
        self.reads[rel] = {'path': str(path), 'sha256': expected, 'size': len(raw)}
        return raw

    def value(self, rel):
        return json.loads(self.read(rel))


def segment_statistics(rows):
    """One row per request; one segment represents its batch's MoE forward."""
    warm = [row for row in rows if row['round'] > 0]
    counts = Counter(n for row in warm for n in row['segment_tokens'])
    if any(sum(row['segment_tokens']) != row['request_suffix_tokens'] for row in rows):
        raise ValueError('segment totals differ from request suffix')
    return {
        'warm_requests': len(warm),
        'warm_segments': sum(counts.values()),
        'warm_request_suffix_le_256': sum(row['request_suffix_tokens'] <= THRESHOLD for row in warm),
        'warm_segments_le_256': sum(count for n, count in counts.items() if n <= THRESHOLD),
        'warm_requests_with_any_segment_le_256': sum(any(n <= THRESHOLD for n in row['segment_tokens']) for row in warm),
        'warm_segment_length_counts': dict(sorted(counts.items())),
        'business_segment_boundary_counts': {str(n): counts[n] for n in (1, 19, 32, 64, 256, 257)},
        'unit': 'per-MoE-forward prefill segment tokens; not request suffix tokens',
    }


def verified_cached_tokens(api, binding, index):
    cached = binding['d0']['cached_tokens']
    reported = api['usage'].get('prompt_tokens_details', {}).get('cached_tokens')
    if reported is None:
        if (index != 0 or cached != 0 or binding['api']['cached_tokens'] !=
                {'independently_verified': False, 'state': 'missing', 'value': None}):
            raise ValueError('only the independently bound cold request may omit API cached tokens')
    elif reported != cached or binding['api']['cached_tokens'] != {
            'independently_verified': True, 'state': 'reported', 'value': cached}:
        raise ValueError('API/D0 cache accounting differs')
    return cached


def read_request(src, group, row, d0_lines):
    index, uid = row['round'], row['uid']
    stem = f'{group}/round-{index:02d}'
    binding = src.value(stem + '.binding.json')
    if binding['schema'] != 'ft_t06_ordinary_binding/v8' or binding['verdict'] != 'worker_input_uid_token_bound':
        raise ValueError('ordinary worker binding differs')
    payload_raw = src.read(stem + '.payload.json')
    if binding['payload_source'] != {'path': str(src.root / (stem + '.payload.json')), 'sha256': sha(payload_raw)}:
        raise ValueError('payload binding differs')
    payload = json.loads(payload_raw)
    if (payload['model'] != 'Qwen3.8-Flash-Next-NVFP4'
            or payload['temperature'] != 0 or payload['max_tokens'] != 2048
            or payload['stream'] is not True or payload['stream_options'] != {'include_usage': True}):
        raise ValueError('payload protocol differs')
    worker = binding['worker_input']
    ids_rel = src.relative(worker['input_ids_path'])
    ids_raw = src.read(ids_rel)
    ids = json.loads(ids_raw)
    if (worker['uid'] != uid or len(ids) != worker['input_tokens']
            or any(type(n) is not int or n < 0 for n in ids)
            or json.dumps(ids, separators=(',', ':')).encode('ascii') != ids_raw
            or sha(ids_raw) != worker['input_ids_sha256']
            or sha(ids_raw) != worker['input_ids_file_sha256']):
        raise ValueError('worker input identity differs')
    api_raw = src.read(stem + '.api.json')
    api = json.loads(api_raw)
    if (sha(api_raw) != binding['api']['sha256'] or api['uid'] != uid
            or api['usage'] != binding['api']['usage']):
        raise ValueError('API binding differs')
    segments = binding['d0']['schedule']
    for segment in segments:
        event = d0_lines[segment['line'] - 1]
        # A single business request per forward is required for this derivation.
        if event['reqs'] != [{k: segment[k] for k in ('rid', 'new_tokens', 'cached_tokens')}]:
            raise ValueError('D0 segment is not the bound single-request forward')
        if segment['rid'] != uid or segment['new_tokens'] <= 0:
            raise ValueError('D0 segment UID/length differs')
    routes = [record for record in binding['route']['records'] if record['phase'] == 'prefill']
    if [item['n_tokens'] for item in routes] != [item['new_tokens'] for item in segments]:
        raise ValueError('route/D0 segment order or length differs')
    for route in routes:
        rel = src.relative(route['path'])
        raw = src.read(rel)
        meta = json.loads(raw)
        if (sha(raw) != route['json_sha256'] or meta['seq'] != route['seq']
                or meta['phase'] != 'prefill' or meta['t'] != route['n_tokens']
                or meta['reqs'] != [{'rid': uid, 'n_tokens': route['n_tokens']}]
                or meta['layer_ids'] != list(range(48))):
            raise ValueError('route metadata differs')
    suffix = sum(item['new_tokens'] for item in segments)
    cached = verified_cached_tokens(api, binding, index)
    if (suffix != row['n'] or suffix != binding['d0']['new_tokens']
            or suffix != binding['route']['prefill_tokens']
            or worker['input_tokens'] - cached != suffix):
        raise ValueError('request suffix accounting differs')
    return {
        'group': group, 'round': index, 'uid': uid,
        'request_suffix_tokens': suffix,
        'segment_tokens': [item['new_tokens'] for item in segments],
        'input_tokens': len(ids), 'input_ids_path': ids_rel,
        'cached_tokens_d0': cached, 'api_cached_tokens': binding['api']['cached_tokens'],
        'input_ids_sha256': sha(ids_raw),
        'payload_path': stem + '.payload.json', 'payload_sha256': sha(payload_raw),
        'binding_path': stem + '.binding.json',
        'api_completion_tokens': api['usage']['completion_tokens'],
        'prefill_routes': routes,
    }


def derive(source, destination):
    src = SealedInputs(source)
    rows = []
    for group, count in GROUPS.items():
        summary = src.value(group + '/route_summary.json')
        if summary['ordinary_worker_token_bound'] is not True or len(summary['suffix_tokens']) != count:
            raise ValueError('group ordinary binding/count differs')
        d0 = [json.loads(line) for line in src.read(group + '/d0_prefill.jsonl').splitlines() if line]
        if [r['round'] for r in summary['suffix_tokens']] != list(range(count)):
            raise ValueError('request history order differs')
        rows.extend(read_request(src, group, row, d0) for row in summary['suffix_tokens'])
    selected = [row for row in rows if row['group'] == 'G_seed12k' and row['round'] <= 2]
    if [row['segment_tokens'] for row in selected] != [[512, 12148], [64, 233], [123]]:
        raise ValueError('frozen minimal history differs')
    # Read only three small prefill NPZs; decode routes are deliberately excluded.
    import numpy as np
    expert_counts = []
    for row in selected[1:]:
        for route in row['prefill_routes']:
            rel = src.relative(route['npz'])
            raw = src.read(rel)
            if sha(raw) != route['npz_sha256']:
                raise ValueError('route NPZ binding differs')
            with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
                ids = archive['expert_ids']
                if ids.shape != (48, route['n_tokens'], 10) or ids.dtype != np.int16 or ids.min() < 0 or ids.max() >= 512:
                    raise ValueError('target route tensor geometry differs')
                expert_counts.append({'round': row['round'], 'segment_tokens': route['n_tokens'],
                    'source': rel, 'sha256': sha(raw),
                    'unique_experts_by_layer': [int(np.unique(ids[layer]).size) for layer in range(48)]})
    result = {
        'schema': 'ft_d12_sealed_segment_inputs/v1',
        'source_round': 'E2-R046g', 'round_sha256': ROUND_SHA, 'manifest_sha256': MANIFEST_SHA,
        'candidate_commit': '8f6a912ea6066f192c37dc74435efc9da0c7591c',
        'threshold': THRESHOLD, 'statistics': segment_statistics(rows),
        'rows': rows, 'selected_history': selected,
        'selected_prefill_unique_experts': expert_counts,
        'source_bindings': src.reads,
        'replay_contract': {
            'order': [0, 1, 2], 'group': 'G_seed12k', 'payload_changes': [],
            'same_candidate_both_arms': True, 'thresholds': [0, THRESHOLD],
            'moe_prefill_overlap_both_arms': False,
            'max_tokens': 2048, 'temperature': 0,
            'ordinary_sse_only': True, 'historical_outputs_are_not_new_acceptance': True,
            'fresh_worker_inputs_and_segments_must_be_verified': True,
            'historical_segment_shapes_are_replay_expectations_not_guarantees': True,
        },
        'gpu_validation_performed': False, 'performance_claims': False,
        'limits': ['Only selected three short prefill tensors have expert-count analysis.',
                   'No 1/19/32/256/257 business segment observed in the bound sample.',
                   'Historical route tracing timings are not performance measurements.',
                   'Threshold 256 remains exploratory, not optimal or a release setting.'],
    }
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=False)
    for row in selected:
        for role in ('payload_path', 'input_ids_path', 'binding_path'):
            rel = row[role]
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read(rel))
    (dest / 'binding.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(dest / 'binding.json'), 'sha256': sha((dest / 'binding.json').read_bytes()),
                      'statistics': result['statistics'], 'source_files_verified': len(src.reads)}, sort_keys=True))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    derive(args.source, args.output)
