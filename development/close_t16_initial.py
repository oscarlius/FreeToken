"""Initial T16 closure only; rejects an existing round.json/history/manifest."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rid')
    parser.add_argument('--batch', type=int, required=True)
    parser.add_argument('--review', required=True, help='new read-only independent review JSON')
    args = parser.parse_args()
    if not re.fullmatch(r'E2-pre-gate-D(?:00|01|02)', args.rid):
        parser.error('unexpected assigned RID')
    directory = Path('/data2/_shared/runs/ft_rounds') / args.rid
    gate = json.loads((directory / f'gate_batch{args.batch}.json').read_text())
    review_path = Path(args.review)
    review = json.loads(review_path.read_text())
    if review.get('verdict') != 'PASS' or review.get('rid') != args.rid or review.get('batch') != args.batch:
        raise ValueError('independent 01 review missing or failed')
    if gate['proposed_verdict'] != 'kept':
        raise ValueError('gate failed')
    status = json.loads((directory / f'status_batch{args.batch}.json').read_text())
    if status['state'] != 'complete':
        raise ValueError('batch not terminal complete')
    pid_state = Path(f'/proc/{status["batch_pid"]}/stat')
    if pid_state.exists() and pid_state.read_text().split(') ', 1)[1][0] != 'Z':
        raise ValueError('batch process still alive')
    for name in ('round.json', 'round_history', 'MANIFEST.sha256'):
        if (directory / name).exists():
            raise ValueError(f'closure artifact already exists: {name}')
    for path in directory.rglob('*'):
        if path.is_symlink() or path.stat().st_uid != os.geteuid():
            raise ValueError(f'foreign owner/symlink: {path}')
    required = ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt', 'ENV.txt')
    for arm in gate['arms']:
        if not re.fullmatch(r'[A-Za-z0-9_]+', arm):
            raise ValueError(f'invalid arm name: {arm}')
        for name in required:
            path = directory / arm / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f'missing required artifact: {path}')
    wrapper = directory / f'batch{args.batch}.sh'
    if not wrapper.is_file():
        raise ValueError('actual batch wrapper missing')
    if not (directory / 'batch.sh').exists():
        with (directory / 'batch.sh').open('xb') as dst:
            dst.write(wrapper.read_bytes())
    timestamp = datetime.now(timezone(timedelta(hours=8))).strftime('%F %T CST')
    created = timestamp
    batches = [20, 21, 22, 23, 24] if gate['gate'] == 'D01' else [args.batch]
    batch_logs = []
    for number in batches:
        path = directory.parent / f'batch{number}.log'
        batch_logs.append({'path': str(path), 'sha256': digest(path)})
        if number == batches[0]:
            first = path.read_text().splitlines()[0]
            match = re.search(r'start (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', first)
            if match:
                created = match[1] + ' CST'
    arms = {}
    for arm in gate['arms']:
        env = {'FT_DEV_D0': '1'} if (directory / arm / 'd0_prefill.jsonl').exists() else {}
        arms[arm] = {'serve_cmd': arm + '/SERVE_CMD.txt', 'serve_args': arm + '/serve_args.txt',
                     'env': env, 'environment_snapshot': arm + '/ENV.txt'}
    anomalies = []
    if gate['gate'] == 'D01':
        anomalies = [
            {'batch': 20, 'reason': 'user requested D02 before resuming; PARENT completed, NEW stopped during load'},
            {'batch': 21, 'reason': 'local declaration expansion failed before creating arms'},
            {'batch': 22, 'reason': 'runtime PATH omitted; failed before model load'},
            {'batch': 23, 'reason': 'invalid awk resource filter; owned server stopped, no usable sample'},
        ]
    profiles = {key: value for key, value in gate.items() if key in ('layer_major', 'non_layer_major')}
    results = {}
    first_shots = []
    for profile, evidence in profiles.items():
        results[profile] = {'parent_d0_rows': evidence['prefill']['parent_rows'],
                            'new_d0_rows': evidence['prefill']['new_rows'],
                            'all_prefill_events': evidence['prefill']['all_prefill_events']}
        for mode in ('D0', 'PROD'):
            for case, values in evidence[mode].items():
                if not isinstance(values, dict) or 'records' not in values:
                    continue
                results[profile][mode + '_' + case + '_content_chars'] = values['content_chars']
                for side, record in zip(('parent', 'new'), values['records']):
                    first_shots.append({'arm': profile + '/' + mode + '/' + side, 'case': case,
                                        'metric': 'ttft_s', 'value': record['ttft_s'], 'unit': 's'})
    worktree, branch = {
        'D01': ('/data2/FreeToken/wt/e1r008', 'exp/e1r008-anchorcut'),
        'D02': ('/data2/FreeToken/wt/e1ms', 'exp/e1-ms'),
        'D00': ('/data2/FreeToken/wt/e2base', 'e2/base'),
    }[gate['gate']]
    full_commits = set()
    for arm in gate['arms']:
        full_commits.update(re.findall(r'\b' + re.escape(gate['new_commit']) + r'[0-9a-f]{33}\b',
                                       (directory / arm / 'ENV.txt').read_text()))
    if len(full_commits) != 1:
        raise ValueError('cannot resolve exact new commit from environment snapshots')
    document = {
        'schema': 'ft_round/v2', 'round_id': args.rid, 'epoch': 2, 'card': 'T16',
        'title': gate['gate'] + ' default-path losslessness gate', 'parent': 'E2-pre',
        'created_at': created, 'closed_at': timestamp,
        'executor': '01 test executor, independent native verifier review',
        'base': {'repo': 'fork/FreeToken', 'commit': full_commits.pop(), 'branch': branch,
                 'worktree': worktree, 'freetoken_file': worktree + '/python/freetoken/__init__.py',
                 'parent_commit': gate['parent_commit'], 'code_version': gate['gate'] + '-candidate@' + gate['new_commit'],
                 'upstream_base': 'd3512b4'},
        'serve': {'arms': arms}, 'design': {'order': gate['arms'], 'temperature': 0,
                 'cold_target_tokens': 32052, 'max_output_tokens': 128,
                 'first_shot_policy': 'preserved separately, timings are not losslessness criteria',
                 'parent_reused_from_batch20': gate['gate'] == 'D01'},
        'results': results, 'first_shots': first_shots, 'gate_checks': profiles,
        'sub_conclusions': [{'id': 'SC1', 'text': 'Default full output, prefill sequence and byte counters match',
                             'status': 'kept', 'evidence': [f'gate_batch{args.batch}.json', review_path.name]}],
        'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
        'anomalies': anomalies, 'batch_logs': batch_logs, 'manifest': 'MANIFEST.sha256',
        'independent_review_sha256': digest(review_path),
    }
    with (directory / 'round.json').open('x') as handle:
        handle.write(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    history = directory / 'round_history'
    history.mkdir()
    snapshot = history / 'round.v001.json'
    with snapshot.open('xb') as handle:
        handle.write((directory / 'round.json').read_bytes())
    (history / 'SHA256SUMS').write_text(digest(snapshot) + '  round.v001.json\n')
    files = sorted(path for path in directory.rglob('*') if path.is_file()
                   and path.name not in ('round.json', 'MANIFEST.sha256') and history not in path.parents)
    manifest = directory / 'MANIFEST.sha256'
    manifest.write_text(''.join(digest(path) + '  ./' + str(path.relative_to(directory)) + '\n' for path in files))
    for path in sorted(directory.rglob('*'), reverse=True):
        path.chmod(path.stat().st_mode & ~0o222)
    directory.chmod(directory.stat().st_mode & ~0o222)
    print(json.dumps({'rid': args.rid, 'closed_at': timestamp, 'manifest_sha256': digest(manifest),
                      'manifest_files': len(files), 'round_sha256': digest(directory / 'round.json'),
                      'verdict': 'pending_review', 'proposed_verdict': 'kept'}))


if __name__ == '__main__':
    main()
