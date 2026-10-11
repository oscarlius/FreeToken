set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, pathlib, subprocess
root = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R016')

def small(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('unbounded artifact: ' + str(path))
    return json.loads(path.read_text())

def tail(path, limit=4000):
    if not path.is_file() or path.is_symlink():
        return None
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - limit))
        return stream.read(limit).decode('utf-8', errors='replace')

def process(pid):
    path = pathlib.Path('/proc') / str(pid)
    try:
        return {'pid': pid, 'state': path.joinpath('stat').read_text().partition(') ')[2][0],
                'argv': path.joinpath('cmdline').read_bytes().replace(b'\0', b' ').decode()}
    except FileNotFoundError:
        return {'pid': pid, 'absent': True}

result = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'status': small(root / 'status_batch42.json'), 'batch_process': process(2672941),
          'lock_present': pathlib.Path('/data2/_shared/gpu.lock').exists(),
          'batch_log_tail': tail(root.parent / 'batch42.log')}
if (result['status']['rid'], result['status']['batch'], result['status']['batch_pid']) != ('E2-R016', 42, 2672941):
    raise ValueError('wrong assigned batch')
for arm in ('B1', 'B2', 'B3'):
    directory = root / arm
    if not directory.is_dir():
        continue
    detail = {}
    owned = directory / 'owned_process.json'
    if owned.is_file():
        detail['owned'] = small(owned)
        detail['owned_process'] = process(detail['owned']['pid'])
    replay = directory / 'reverse_cold.json'
    if replay.is_file():
        raw = small(replay)
        detail['params'] = (raw.get('meta') or {}).get('params')
        detail['rows'] = [{key: row.get(key) for key in ('round', 'messages_sha', 'error', 'dry_run',
                          'finish_reason', 'completion_tokens', 'prompt_tokens')}
                          for row in raw.get('rounds', [])]
        for summary, row in zip(detail['rows'], raw.get('rounds', [])):
            summary['tool_calls'] = row.get('tool_calls')
            summary['keys'] = sorted(row)
    tokens = sorted((directory / 'logits').glob('tokens_uid*_pid*.json'))
    if len(tokens) > 24:
        raise ValueError('terminal stream exceeded assigned arm')
    detail['terminals'] = []
    for path in tokens:
        value = small(path)
        detail['terminals'].append({'name': path.name, 'uid': value.get('uid'), 'pid': value.get('pid'),
                                   'prompt_length': value.get('prompt_length'),
                                   'generated_length': len(value.get('generated_ids', [])),
                                   'finish_reason': value.get('finish_reason')})
    detail['replay_log_tail'] = tail(directory / 'reverse_cold.log')
    detail['serve_log_tail'] = tail(directory / 'serve.log')
    result[arm] = detail
print(json.dumps(result, ensure_ascii=False, allow_nan=False))
PY
