"""Main-session (non-author) independent review of the completed D09FIX T16 batch167.

Read-only over the raw round directory; writes one sealed review JSON (schema mirrors the
batch163 review consumed by close_t16_batch163.py). Never starts a service or touches the GPU.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

RID = 'E2-D09FIX-T16-20261011'
BATCH = 167
CANDIDATE = '7d8d389ee5d85de7e4f8e533f35c27f4c4c02690'
PARENT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
RUN = Path('/data2/_shared/runs/ft_rounds') / RID
LAUNCH = Path('/data2/FreeToken/runs/dev_T16') / f'launch_{RID}_batch{BATCH}.json'
ARMS = tuple(n + f'_b{BATCH}' for n in (
    'PARENT', 'NEW', 'PARENT_P', 'NEW_P',
    'CHUNK_PARENT', 'CHUNK_NEW', 'CHUNK_PARENT_P', 'CHUNK_NEW_P'))
PAIRS = (('PARENT', 'NEW', 'det.json'), ('PARENT_P', 'NEW_P', 'det.json'),
         ('CHUNK_PARENT', 'CHUNK_NEW', 'chunked.json'), ('CHUNK_PARENT', 'CHUNK_NEW', 'short.json'),
         ('CHUNK_PARENT_P', 'CHUNK_NEW_P', 'chunked.json'), ('CHUNK_PARENT_P', 'CHUNK_NEW_P', 'short.json'))
POST = re.compile(r'POST /v1/chat/completions HTTP/1\.1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def alive(pid, start_ticks):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return False
    return fields[0] != 'Z' and int(fields[19]) == start_ticks


def output_identity():
    out = {}
    for a, b, name in PAIRS:
        da, db = read(RUN / f'{a}_b{BATCH}' / name), read(RUN / f'{b}_b{BATCH}' / name)
        ra, rb = da['record'], db['record']
        out[f'{a}_b{BATCH}:{b}_b{BATCH}:{name}'] = {
            'text_equal': da['text'] == db['text'],
            'events': [da['events'], db['events']],
            'finish_reason': [ra['finish_reason'], rb['finish_reason']],
            'prompt_completion_tokens': [[ra['prompt_tokens'], ra['completion_tokens']],
                                         [rb['prompt_tokens'], rb['completion_tokens']]],
        }
    return out


def main(out_path):
    files = {str(p.relative_to(RUN)): sha(p) for p in sorted(RUN.rglob('*')) if p.is_file()}
    status, gate, binding = read(RUN / 'status_batch167.json'), read(RUN / f'gate_batch{BATCH}.json'), read(RUN / 'candidate_binding.json')
    launch = read(LAUNCH)
    identity = output_identity()
    post_counts = {arm: len(POST.findall((RUN / arm / 'serve.log').read_text(errors='replace'))) for arm in ARMS}
    expected_counts = {arm: (13 if arm.startswith('CHUNK_') else 12) for arm in ARMS}
    pid_absent = {}
    for arm in ARMS:
        birth = read(RUN / arm / 'owned_process.json')['birth']
        pid_absent[arm] = not alive(birth['pid'], birth['start_ticks'])
    checks = {
        'raw_file_count_160': len(files) == 160,
        'round_json_absent': not (RUN / 'round.json').exists(),
        'manifest_absent': not (RUN / 'MANIFEST.sha256').exists(),
        'status_pending_review': status.get('state') == 'complete_measurements_pending_review'
                                 and status.get('batch') == BATCH and status.get('rid') == RID,
        'gate_kept_and_bound': gate.get('proposed_verdict') == 'kept' and tuple(gate.get('arms', [])) == ARMS
                               and gate.get('parent_commit') == PARENT and gate.get('new_commit') == CANDIDATE,
        'binding_default_off': binding.get('new_commit') == CANDIDATE and binding.get('parent_commit') == PARENT
                               and binding.get('default_off_public_flag') == {'enable_message_boundary_ckpt': False},
        'all_text_equal': all(v['text_equal'] for v in identity.values()),
        'all_finish_length': all(set(v['finish_reason']) == {'length'} for v in identity.values()),
        'post_counts_match': post_counts == expected_counts and sum(post_counts.values()) == 100,
        'all_service_pids_absent': all(pid_absent.values()),
        'launch_binding': launch.get('rid') == RID and launch.get('batch') == BATCH
                          and launch.get('candidate_commit') == CANDIDATE,
    }
    verdict = 'PASS' if all(checks.values()) else 'FAIL'
    raw_map_canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    review = {
        'schema': 'ft_d09fix_t16_batch167_independent_review/v1',
        'rid': RID, 'batch': BATCH, 'candidate_commit': CANDIDATE, 'parent_commit': PARENT,
        'actual_services': 8, 'actual_generation_calls': sum(post_counts.values()),
        'verdict': verdict,
        'reviewer': 'main_session_non_author (plan/GEMINI_OOM_HYBRID_REVIEW_20261011.md lineage)',
        'reviewed_at': datetime.now().astimezone().isoformat(),
        'review_scope': 'completed raw T16 default-off identity measurement only; no T17, performance, GPU rerun, or product acceptance',
        'closure_conditions': 'Root closure helper must revalidate exact raw file map, child/groups/ports, GPU-idle/lock state, '
                              'and canonical closer/writer hashes immediately before writing pending round.json; this review does not replace those checks.',
        'checks': checks,
        'evidence': {'output_identity': identity, 'post_counts': post_counts, 'post_total': sum(post_counts.values()),
                     'pid_absent_now': pid_absent, 'status_state': status.get('state'),
                     'gate_proposed_verdict': gate.get('proposed_verdict'),
                     'default_off_public_flag': binding.get('default_off_public_flag'),
                     'round_json_absent': checks['round_json_absent'], 'manifest_absent': checks['manifest_absent']},
        'original_raw_file_count': len(files),
        'original_raw_files_sha256': files,
        'original_raw_map_sha256': hashlib.sha256(raw_map_canonical).hexdigest(),
        'original_raw_map_formula': "sha256(json.dumps(map, sort_keys=True, separators=(',', ':')))",
        'generator_sha256': sha(__file__),
    }
    out = Path(out_path)
    with out.open('x', encoding='utf-8') as handle:
        json.dump(review, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write('\n')
    os.chmod(out, 0o444)
    print(json.dumps({'verdict': verdict, 'checks': checks, 'sha256': sha(out)}, ensure_ascii=False))
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
