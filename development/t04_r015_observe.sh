set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime, json, pathlib, subprocess
root = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R015')
def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('artifact outside bounded regular JSON contract: ' + str(path))
    return json.loads(path.read_text())
def process(pid):
    path = pathlib.Path('/proc') / str(pid)
    try:
        return {'pid': pid, 'state': path.joinpath('stat').read_text().partition(') ')[2][0],
                'argv': path.joinpath('cmdline').read_bytes().replace(b'\0', b' ').decode()}
    except FileNotFoundError:
        return {'pid': pid, 'absent': True}
def tail(path, limit=3000):
    if not path.is_file() or path.is_symlink():
        return None
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - limit))
        return stream.read(limit).decode('utf-8', errors='replace')
status = read(root / 'status_batch43.json')
if (status['rid'], status['batch'], status['batch_pid']) != ('E2-R015', 43, 2749339):
    raise ValueError('wrong assigned T04 batch')
result = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': status,
          'batch_process': process(2749339), 'lock_present': pathlib.Path('/data2/_shared/gpu.lock').exists()}
for arm in ('candidate_boundary', 'restore', 'recompute', 'legal'):
    path = root / arm
    if not path.is_dir():
        continue
    detail = {'health_recorded': (path / 'health.json').is_file()}
    if (path / 'owned_process.json').is_file():
        detail['owned'] = read(path / 'owned_process.json')
        detail['process'] = process(detail['owned']['pid'])
    if (path / 'capture.json').is_file():
        detail['capture'] = read(path / 'capture.json')
    detail['log_tail'] = tail(path / 'logits_capture.log')
    index = path / 'logits/index.jsonl'
    if index.is_file():
        if index.is_symlink() or index.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('unbounded logits index')
        rows = [json.loads(row) for row in index.read_text().splitlines() if row.strip()]
        if len(rows) > 128:
            raise ValueError('unbounded logits index record count')
        detail['logits_index'] = [{key: row.get(key) for key in ('uid', 'seq', 'length', 'extra')}
                                  for row in rows if row.get('kind') == 'logits']
    if status['state'] == 'error':
        detail['serve_log_tail'] = tail(path / 'serve.log')
    result[arm] = detail
if status['state'] != 'running':
    result['batch_log_tail'] = tail(root.parent / 'batch43.log')
    for name in ('round_metadata.json', 't04_phase2_error.json'):
        if (root / name).is_file():
            result[name] = read(root / name)
    result['port_8095'] = subprocess.run(['ss', '-ltnp', 'sport = :8095'], capture_output=True, text=True, check=True).stdout
print(json.dumps(result, ensure_ascii=False, allow_nan=False))
PY
