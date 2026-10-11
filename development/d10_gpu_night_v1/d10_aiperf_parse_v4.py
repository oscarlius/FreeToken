"""Strict reader for raw AIPerf records, never summary-only statistics."""
from __future__ import annotations

import json
from pathlib import Path


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from _walk(child)
    elif isinstance(value, list):
        for child in value: yield from _walk(child)


def parse_profile(directory: Path) -> list[dict]:
    records = []
    for path in directory.rglob('*'):
        if not path.is_file() or path.suffix not in {'.json', '.jsonl'}: continue
        for line in path.read_text(encoding='utf-8').splitlines():
            try: values = list(_walk(json.loads(line)))
            except json.JSONDecodeError: continue
            for value in values:
                usage = value.get('usage') if isinstance(value.get('usage'), dict) else value
                completion = usage.get('completion_tokens')
                # A raw response record must identify a request and include TTFT/decode.
                request_id = value.get('request_id') or value.get('id') or value.get('request_index')
                ttft = value.get('ttft') or value.get('time_to_first_token')
                decode = value.get('decode_tokens_per_second') or value.get('output_tokens_per_second')
                if request_id is not None and isinstance(completion, int) and ttft is not None and decode is not None:
                    records.append({'request_id': str(request_id), 'completion_tokens': completion,
                                    'ttft': float(ttft), 'decode_tokens_per_second': float(decode)})
    unique = {row['request_id']: row for row in records}
    return list(unique.values())


def validate_profiles(root: Path) -> dict:
    parsed = {index: parse_profile(root / f'profile{index}') for index in range(4)}
    for index, rows in parsed.items():
        if len(rows) != 2: raise RuntimeError(f'profile {index} lacks two actual raw response records')
    for index in (0, 1):
        if any(row['completion_tokens'] <= 30 for row in parsed[index]):
            raise RuntimeError('original R045 profile has completion <= 30')
    for index in (2, 3):
        if [row['completion_tokens'] for row in parsed[index]] != [256, 256]:
            raise RuntimeError('ignore-EOS profile does not contain exact 256 outputs')
    return parsed
