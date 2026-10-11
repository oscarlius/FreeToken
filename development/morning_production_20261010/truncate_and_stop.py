"""07:55 authority: close the exact observation before the frozen production stop.

This operator entry never starts a test or releases another process's GPU lock.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/data2/FreeToken')
NIGHT = ROOT / 'development/night_execution_20261009'
APPROVAL = 'RESTORE481-NIGHT-20261009-01'
RUN = ROOT / 'runs/production' / APPROVAL
OBSERVER = ROOT / 'development/night_restore_20261009/observe_overnight.py'
COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0],
                'argv': [x.decode() for x in argv if x]}
    except FileNotFoundError:
        return None


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def preflight(review_path):
    # The root supplies the independently accepted candidate review, never a
    # config-only readiness label. It is archived with the stop receipt.
    review_path = Path(review_path)
    binding_path = NIGHT / 'MORNING_GPU_ADMISSION.json'
    if (binding_path.is_symlink() or not binding_path.is_file()
            or binding_path.stat().st_mode & 0o222):
        raise RuntimeError('sealed root admission binding is required')
    binding = json.loads(binding_path.read_text())
    if (binding.get('schema') != 'ft_morning_first_gpu_admission/v1'
            or binding.get('root_approved') is not True
            or binding.get('reviewer') not in ('morning_a_r067_retry2', 'morning_b_s4_r044b', 'root')
            or binding.get('reviewer') == binding.get('author')
            or binding.get('review_path') != str(review_path)
            or review_path.is_symlink() or not review_path.is_file()
            or sha(review_path) != binding.get('review_sha256')):
        raise RuntimeError('independent review binding differs')
    review = json.loads(review_path.read_text())
    verdict = review.get('verdict')
    if verdict not in ('PASS', 'APPROVE_GPU_STARTUP', 'APPROVE_GPU_ADMISSION',
                       'PASS_STARTUP_ADMISSION', 'APPROVED_FOR_GPU'):
        raise RuntimeError('a passing independent GPU startup review is required')
    if not binding.get('source_sha256'):
        raise RuntimeError('candidate source bindings absent')
    for name, digest in binding['source_sha256'].items():
        path = Path(name)
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or sha(path) != digest):
            raise RuntimeError('candidate source changed: ' + name)
    worktree = Path(binding['worktree'])
    if worktree.is_symlink() or worktree.parent not in (ROOT / 'wt', Path('/data2/Strata/wt')):
        raise RuntimeError('candidate worktree scope differs')
    head = subprocess.check_output(['git', '-C', str(worktree), 'rev-parse', 'HEAD'], text=True).strip()
    if head != binding['candidate_commit']:
        raise RuntimeError('reviewed candidate commit differs')
    old = ROOT / 'development/night_restore_20261009'
    manifest_path = old / 'SOURCE_MANIFEST.json'
    if sha(manifest_path) != '495654db3755f93e62dd7f9bfbb70e36adbed5282d0bae8ff88f295f335069bc':
        raise RuntimeError('frozen stop package manifest changed')
    for name, digest in json.loads(manifest_path.read_text())['files'].items():
        if sha(old / name) != digest:
            raise RuntimeError('frozen stop source changed: ' + name)
    owner = json.loads((ROOT / 'run/production.active.json').read_text())
    if owner.get('approval_id') != APPROVAL or owner.get('commit') != COMMIT:
        raise RuntimeError('foreign production owner')
    for key in ('supervisor', 'service'):
        expected = owner[key]
        live = identity(expected['pid'])
        if not live or live['start_ticks'] != expected['start_ticks'] or live['state'] == 'Z':
            raise RuntimeError('production identity changed: ' + key)
    start = json.loads((RUN / 'overnight_observation/start.json').read_text())
    if start['owner'] != owner:
        raise RuntimeError('observation owner differs')
    pid = start['observer_pid']
    observer = identity(pid)
    wanted = [str(OBSERVER), '--run-dir', str(RUN), '--out-dir',
              str(RUN / 'overnight_observation'), '--until', start['until']]
    if not observer or observer['argv'][1:] != wanted or observer['state'] == 'Z':
        raise RuntimeError('observer identity differs')
    return owner, start, observer, review_path


def execute(review_path):
    owner, start, observer, review_path = preflight(review_path)
    obs = RUN / 'overnight_observation'
    terminal = obs / 'terminal.json'
    if terminal.exists():
        raise RuntimeError('refuse to replace an existing observation terminal')
    # Freeze and check PID birth immediately before the only observer signal.
    live = identity(observer['pid'])
    if live != observer:
        raise RuntimeError('observer changed before truncation')
    os.kill(observer['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        live = identity(observer['pid'])
        if live is None or live['state'] == 'Z':
            break
        if live['start_ticks'] != observer['start_ticks']:
            raise RuntimeError('observer PID was reused')
        time.sleep(.1)
    else:
        raise RuntimeError('observer did not stop; production remains online')
    rows = [json.loads(line) for line in (obs / 'samples.jsonl').read_text().splitlines() if line.strip()]
    now = time.time()
    result = {'classification': 'truncated', 'started_at': start['at'], 'ended_at': now,
              'written_at': datetime.now().astimezone().isoformat(),
              'samples': len(rows), 'last_sample': rows[-1] if rows else None,
              'actual_window_seconds': now - start['at'],
              'original_until': start['until'], 'observer': observer,
              'reason': 'user 07:55 revision: independently ready GPU item',
              'eligible_to_request_push_approval': False, 'push_approved': False,
              'push_executed': False, 'generation_requests': 0,
              'samples_sha256': sha(obs / 'samples.jsonl'),
              'independent_startup_review': str(review_path),
              'independent_startup_review_sha256': sha(review_path)}
    write_new(terminal, result)
    # Reuse the already independently reviewed stop controller and its owner/
    # birth/lock checks; no broad process killing or manual lock deletion.
    stop = ROOT / 'development/night_restore_20261009/stop_approved_restore.py'
    completed = subprocess.run([str(ROOT / 'venv/bin/python'), str(stop)])
    receipt = {'at': datetime.now().astimezone().isoformat(),
               'stop_exit_code': completed.returncode, 'owner': owner,
               'observation_terminal_sha256': sha(terminal),
               'stopped_receipt_exists': (RUN / 'stopped.json').is_file()}
    write_new(NIGHT / 'MORNING_PRODUCTION_STOP.json', receipt)
    with (NIGHT / 'COORDINATION_LOG.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'at': receipt['at'], 'event': 'morning_production_stop',
                                 **receipt}, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    if completed.returncode or not receipt['stopped_receipt_exists']:
        raise RuntimeError('production stop not closed; no GPU admission')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    if args.execute:
        execute(args.review)
    elif args.preflight:
        owner, start, observer, review = preflight(args.review)
        print(json.dumps({'owner': owner['approval_id'], 'observer': observer,
                          'review_sha256': sha(review), 'mutations': False}))
    else:
        parser.error('choose --preflight or --execute')
