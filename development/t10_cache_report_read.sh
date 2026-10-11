#!/usr/bin/env bash
# Read-only evidence extractor. Run remotely with:
#   python development/remote.py development/t10_cache_report_read.sh
set -euo pipefail

CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib
import json
import re
from pathlib import Path

ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R006')
ARMS = ('B1', 'B2', 'B3')
PREFILL = re.compile(r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def post_groups(log: Path):
    """Return one ordered prefill group per completed chat request.

    serve.log has neither request IDs nor message digests.  A group is therefore
    the contiguous Prefill lines preceding one POST completion; callers must also
    prove its total equals the ordered replay prompt count.
    """
    groups, current = [], []
    for line_no, line in enumerate(log.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        match = PREFILL.search(line)
        if match:
            new_seq, new_tokens, cached_tokens = map(int, match.groups())
            current.append({
                'line': line_no,
                'new_seq': new_seq,
                'new_tokens': new_tokens,
                'cached_tokens': cached_tokens,
            })
        if 'POST /v1/chat/completions' in line:
            # Readiness/health probes can be a completed chat request with no
            # Prefill log.  It is not a replay group and is deliberately omitted.
            if current:
                groups.append(current)
                current = []
    # The server can write its final Prefill line after emitting the HTTP access
    # record, so retain that final ordered group as well.
    if current:
        groups.append(current)
    return groups


def vector(rows, groups, kind):
    if len(rows) != 12 or len(groups) != 12:
        raise ValueError(f'{kind} requires exactly 12 replay rows and 12 POST groups')
    output = []
    for ordinal, (row, group) in enumerate(zip(rows, groups)):
        message_sha = row.get('messages_sha')
        trace_sha = row.get('trace_messages_sha')
        prompt = row.get('prompt_tokens')
        if not isinstance(message_sha, str) or message_sha != trace_sha:
            raise ValueError(f'{kind}[{ordinal}] lacks a messages_sha/trace_messages_sha join')
        if type(prompt) is not int:
            raise ValueError(f'{kind}[{ordinal}] prompt_tokens is not an integer')
        new = sum(item['new_tokens'] for item in group)
        cached = sum(item['cached_tokens'] for item in group)
        if new + cached != prompt:
            raise ValueError(f'{kind}[{ordinal}] log total {new}+{cached} != replay prompt {prompt}')
        output.append({
            'order': ordinal,
            'round': row.get('round'),
            'messages_sha': message_sha,
            'prompt_tokens': prompt,
            'response_cached_tokens': row.get('cached_tokens'),
            'response_recomputed_tokens': row.get('recomputed_tokens'),
            'server_new_tokens': new,
            'server_cached_tokens': cached,
            'serve_log_line_start': group[0]['line'],
            'serve_log_line_end': group[-1]['line'],
            'prefill_lines': group,
        })
    return output


def cache_report_disabled(args: dict) -> bool:
    value = args.get('enable_cache_report')
    if value not in ('False', 'True'):
        raise ValueError(f'unexpected enable_cache_report value: {value!r}')
    return value == 'False'


admission = read_json(ROUND / 'admission.json')
trace = Path(admission['trace'])
if not trace.is_file():
    raise FileNotFoundError(f'admitted trace missing: {trace}')
analysis = {
    'schema': 'ft_cache_report_analysis/v1',
    'round_id': ROUND.name,
    'card': admission.get('card'),
    'admission_sha256': sha256(ROUND / 'admission.json'),
    'trace_path': str(trace),
    'trace_sha256': sha256(trace),
    'binding_limit': (
        'serve.log records neither request IDs nor message digests; a server group is bound to a replay row '
        'only by POST order and exact server_new_tokens + server_cached_tokens == replay.prompt_tokens. '
        'Replay rows separately prove messages_sha == trace_messages_sha.'
    ),
    'arms': {},
}
for name in ARMS:
    arm = ROUND / name
    log = arm / 'serve.log'
    args_path = arm / 'serve_args.txt'
    cold_path = arm / 'reversecold.json'
    warm_path = arm / 'forwardwarm.json'
    args = read_json(args_path)
    groups = post_groups(log)
    if len(groups) != 24:
        raise ValueError(f'{name}: expected 24 POST groups, found {len(groups)}')
    cold = read_json(cold_path)['rounds']
    warm = read_json(warm_path)['rounds']
    cold_vector = vector(cold, groups[:12], 'reversecold')
    warm_vector = vector(warm, groups[12:], 'forwardwarm')
    if any(row['response_cached_tokens'] != 0 for row in cold_vector + warm_vector):
        raise ValueError(f'{name}: expected disabled API cache reporting to yield response cached_tokens=0')
    analysis['arms'][name] = {
        'sha256': {
            'serve_log': sha256(log),
            'serve_args': sha256(args_path),
            'reversecold_replay': sha256(cold_path),
            'forwardwarm_replay': sha256(warm_path),
        },
        'enable_cache_report_disabled': cache_report_disabled(args),
        'messages_sha_binding': {
            'reversecold_rows': len(cold_vector),
            'forwardwarm_rows': len(warm_vector),
            'all_replay_rows_join_trace_messages_sha': True,
        },
        'ordered_post_groups': {
            'count': len(groups),
            'reversecold_groups': [group[0]['line'] for group in groups[:12]],
            'forwardwarm_groups': [group[0]['line'] for group in groups[12:]],
        },
        'reversecold_12': cold_vector,
        'forwardwarm_12': warm_vector,
    }
print(json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True))
PY
