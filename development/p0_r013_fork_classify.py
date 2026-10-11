#!/usr/bin/env python3
"""Read-only classification of sealed E2-R013 fork K=1 FP32 captures."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(round_dir: Path) -> dict[str, Any]:
    manifest = round_dir / 'MANIFEST.sha256'
    checked = 0
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, separator, relative = line.partition('  ')
        target = (round_dir / relative).resolve()
        if (not separator or len(digest) != 64 or round_dir.resolve() not in target.parents
                or not target.is_file() or sha256(target) != digest):
            raise ValueError(f'manifest mismatch: {relative}')
        checked += 1
    history = round_dir / 'round_history/round.v001.json'
    current = round_dir / 'round.json'
    if not history.is_file() or sha256(history) != sha256(current):
        raise ValueError('round history does not preserve current round.json bytes')
    return {'manifest_sha256': sha256(manifest), 'entries_checked': checked,
            'round_json_sha256': sha256(current), 'phase1_manifest_sha256': sha256(round_dir / 'phase1_manifest.json')}


def verify_parent_token_binding(round_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    parent_phase = round_dir.parent / 'E2-R017' / 'phase1_manifest.json'
    local_phase = round_dir / 'phase1_manifest.json'
    if not parent_phase.is_file():
        raise ValueError(f'missing parent R017 phase1 manifest: {parent_phase}')
    parent = json.loads(parent_phase.read_text(encoding='utf-8'))
    forkpoints = parent.get('forkpoints')
    if parent.get('schema') != 't10_engine_tokens/v1' or parent.get('rid') != 'E2-R017':
        raise ValueError('unexpected parent R017 phase1 schema or RID')
    if not isinstance(forkpoints, list) or len(forkpoints) != 11:
        raise ValueError('parent R017 does not contain exactly eleven forkpoints')

    matched_parent_ordinals: list[int] = []
    binding_keys = ('common_generated_ids', 'first_difference_index', 'k',
                    'messages_sha', 'observed_next_ids', 'prompt_ids')
    for ordinal, result in enumerate(results):
        fork = result.get('forkpoint')
        if not isinstance(fork, dict):
            raise ValueError(f'R013 result {ordinal} lacks forkpoint')
        matches = [
            parent_ordinal for parent_ordinal, parent_fork in enumerate(forkpoints)
            if all(fork.get(key) == parent_fork.get(key) for key in binding_keys)
        ]
        if len(matches) != 1:
            raise ValueError(f'R013 fork {ordinal} has {len(matches)} parent token bindings')
        parent_fork = forkpoints[matches[0]]
        prompt_ids = parent_fork.get('prompt_ids')
        if (not isinstance(prompt_ids, list)
                or any(type(token) is not int for token in prompt_ids)):
            raise ValueError(f'parent fork {matches[0]} prompt_ids are not integer tokens')
        packed = struct.pack(f'<{len(prompt_ids)}i', *prompt_ids)
        if hashlib.sha256(packed).hexdigest() != parent_fork.get('prompt_ids_sha256_int32le'):
            raise ValueError(f'parent fork {matches[0]} prompt token SHA mismatch')
        matched_parent_ordinals.append(matches[0])
    if sorted(matched_parent_ordinals) != list(range(11)):
        raise ValueError('R013 does not bind each parent forkpoint exactly once')
    return {
        'parent_round_id': 'E2-R017',
        'parent_phase1_manifest_sha256': sha256(parent_phase),
        'r013_phase1_byte_equal_to_parent': local_phase.read_bytes() == parent_phase.read_bytes(),
        'schema': parent['schema'],
        'forkpoints': len(forkpoints),
        'stage2_parent_fork_ordinals': matched_parent_ordinals,
        'binding': 'all 11 R013 stage2 forkpoints match exactly one parent forkpoint on messages_sha, prompt_ids, k, first_difference_index, common_generated_ids, and observed_next_ids; parent int32le prompt-token SHA256 was recomputed',
    }


def logits_vector(path: Path):
    import torch
    value = torch.load(path, map_location='cpu', weights_only=True)
    if not isinstance(value, torch.Tensor):
        raise ValueError(f'expected tensor logits: {path}')
    if value.ndim < 1:
        raise ValueError(f'logits tensor has no vocabulary dimension: {path}')
    return value.reshape(-1, value.shape[-1])[-1].float()


def top2(path: Path) -> dict[str, Any]:
    import torch
    values, ids = torch.topk(logits_vector(path), 2)
    return {'top1_token_id': int(ids[0]), 'top1_logit': float(values[0]),
            'top2_token_id': int(ids[1]), 'top2_logit': float(values[1]),
            'top2_margin': float(values[0] - values[1])}


def analysis_bucket(fork_idx: int) -> str:
    # No T10 card threshold exists. This is an explicit descriptive partition,
    # not a scientific gate: index zero; one through ten; and observed 48+ tail.
    if fork_idx == 0:
        return 'token_0'
    if 1 <= fork_idx <= 10:
        return 'early_idx_1_to_10'
    if fork_idx >= 48:
        return 'late_idx_48_plus'
    return 'unclassified_between_11_and_47'


def classify(round_dir: Path) -> dict[str, Any]:
    provenance = verify_manifest(round_dir)
    data = json.loads((round_dir / 'stage2_results.json').read_text(encoding='utf-8'))
    if data.get('schema') != 't10_logits_stage2/v1' or not isinstance(data.get('results'), list):
        raise ValueError('unexpected R013 stage2 results schema')
    parent_binding = verify_parent_token_binding(round_dir, data['results'])
    rows: list[dict[str, Any]] = []
    for ordinal, result in enumerate(data['results']):
        fork = result.get('forkpoint')
        if not isinstance(fork, dict) or type(fork.get('first_difference_index')) is not int:
            raise ValueError(f'fork{ordinal:02d} lacks integer first_difference_index')
        fork_id = f'fork{ordinal:02d}'
        first_idx = fork['first_difference_index']
        a = round_dir / f'{fork_id}_a/logits/logits_0001_dev_logits.pt'
        b = round_dir / f'{fork_id}_b/logits/logits_0001_dev_logits.pt'
        a_top, b_top = top2(a), top2(b)
        import torch
        a_vec, b_vec = logits_vector(a), logits_vector(b)
        if a_vec.shape != b_vec.shape:
            raise ValueError(f'{fork_id} logits shapes differ')
        max_abs_gap = float(torch.max(torch.abs(a_vec - b_vec)))
        compare = json.loads((round_dir / f'{fork_id}_compare.log').read_text(encoding='utf-8'))
        peer = compare.get('peer_vs_recompute', {})
        if peer.get('bitwise_equal') is not True or peer.get('top1_per_position') != [True]:
            raise ValueError(f'{fork_id} compare evidence is not K1 bitwise/top1 equal')
        observed = fork.get('observed_next_ids')
        rows.append({
            'fork_id': fork_id, 'fork_idx': first_idx, 'classification': analysis_bucket(first_idx),
            'input_length': compare.get('input_length'), 'position': compare.get('positions'),
            'observed_next_ids': observed, 'a': a_top, 'b': b_top,
            'max_abs_logit_gap': max_abs_gap,
            'top1_equal': a_top['top1_token_id'] == b_top['top1_token_id'],
            'top2_equal': a_top['top2_token_id'] == b_top['top2_token_id'],
            'compare_top2_margin': peer.get('top2_margin'),
            'compare_log_sha256': sha256(round_dir / f'{fork_id}_compare.log'),
        })
    return {
        'schema': 'p0_r013_fork_classification/v1', 'round_id': 'E2-R013',
        'provenance': provenance,
        'parent_token_binding': parent_binding,
        'protocol': 'Each side used a fresh service process, warmed its own prefix, then captured P+X with K=1. This is not a direct cold-versus-warm request.',
        'classification_definition': {'token_0': 'fork_idx == 0', 'early_idx_1_to_10': '1 <= fork_idx <= 10', 'late_idx_48_plus': 'fork_idx >= 48', 'status': 'descriptive only; no card threshold or scientific PASS gate inferred'},
        'forks': rows,
        'counts': {bucket: sum(row['classification'] == bucket for row in rows) for bucket in ('token_0', 'early_idx_1_to_10', 'late_idx_48_plus', 'unclassified_between_11_and_47')},
        'limitations': 'R013 proves pairwise reproducibility under its fresh-process/warm-prefix protocol. It does not establish a cold/warm causal mechanism for these forks.',
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--round-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    value = classify(args.round_dir)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    else:
        print(text, end='')

if __name__ == '__main__':
    main()
