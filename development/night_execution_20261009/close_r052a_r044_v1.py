"""Seal completed rounds, without touching the next independent GPU owner."""
import datetime
import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
PY = str(ROOT / 'venv/bin/python')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def absent(pid, birth):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] == 'Z' or int(fields[19]) != birth
    except FileNotFoundError:
        return True


def close(rid, card, batch, review_name, launch_dir, source_dir, terminal_name, verdict, calls):
    run = ROUNDS / rid
    assert not (run / 'round.json').exists()
    review = HERE / review_name
    judgment = json.loads(review.read_text())
    assert judgment['verdict'].lower() == verdict
    cleanup = json.loads((run / 'owned_cleanup.json').read_text())
    assert cleanup['lock_released'] is True and cleanup['batch'] == batch
    launch = ROOT / launch_dir / f'launch_{rid}_batch{batch}.json'
    binding = json.loads(launch.read_text())
    assert absent(binding['child']['pid'], binding['child']['start_ticks'])
    source = run / source_dir
    owner = json.loads((source / 'owned_process.json').read_text())
    assert absent(owner['birth']['pid'], owner['birth']['start_ticks'])
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            assert fields[0] == 'Z' or int(fields[2]) != owner['birth']['pgid']
        except (FileNotFoundError, ProcessLookupError):
            pass
    arm = run / 'SERVICE_ACTUAL'
    arm.mkdir()
    shutil.copy2(source / 'serve.log', arm / 'serve.log')
    if (source / 'serve_argv.json').exists():
        command = json.loads((source / 'serve_argv.json').read_text())
    else:
        command = json.loads((source / 'service_plan.json').read_text())
    argv = command['argv']; environment = command['environment']
    (arm / 'SERVE_CMD.txt').write_text(shlex.join(argv) + '\n')
    (arm / 'ENV.txt').write_text(json.dumps(environment, indent=2) + '\n')
    lines = [line for line in (source / 'serve.log').read_text().splitlines() if line.startswith('ServerArgs(')]
    assert len(lines) == 1
    (arm / 'serve_args.txt').write_text(lines[0] + '\n')
    for src, name in ((launch, 'launch_receipt.json'), (Path(binding['wrapper']), 'batch.sh'),
                      (Path(binding['batch_log']), f'batch{batch}.log'), (review, 'independent_review.json')):
        shutil.copy2(src, run / name)
    put(run / 'cleanup_readback.json', {'at': datetime.datetime.now().astimezone().isoformat(),
        'owned_child_absent': True, 'owned_group_absent': True, 'lock_released_receipt': True,
        'current_independent_GPU_round_excluded_from_this_closure': True,
        'restore481_required_by0730': True})
    doc = {'schema': 'ft_round/v2', 'round_id': rid, 'card': card, 'batch': batch,
        'retry_of': None, 'retry_index': 0, 'verdict': 'pending_review', 'proposed_verdict': verdict,
        'verdict_history': [], 'retractions': [], 'serve': {'arms': {'SERVICE_ACTUAL': {'raw_source': str(source)}}},
        'base': {'commit': '0aa23431e5b800797543bdecbf35a01045131d7d'},
        'experimental': {'candidate_commit': '0aa23431e5b800797543bdecbf35a01045131d7d'},
        'batch_logs': [{'path': binding['batch_log'], 'sha256': sha(binding['batch_log'])}],
        'actual_services': 1, 'actual_generation_calls': calls, 'product_acceptance': False,
        'result_binding': {name: {'path': name, 'sha256': sha(run / name)} for name in
            (terminal_name, 'owned_cleanup.json', 'cleanup_readback.json')},
        'independent_review': {'path': 'independent_review.json', 'sha256': sha(run / 'independent_review.json')}}
    put(run / 'round.json', doc)
    closer = ROOT / 'runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py'
    assert sha(closer) == 'db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
    result = subprocess.run([PY, str(closer), rid, '--round-root', str(ROUNDS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    app = ROOT / 'scripts/round_json_append.py'
    result = subprocess.run([PY, str(app), str(run), 'verdict', '--new', verdict,
        '--reason', judgment.get('reason', judgment.get('decision', {}).get('reason', verdict)),
        '--evidence', str(run / terminal_name), str(run / 'independent_review.json'), '--by', 'root'],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([PY, str(app), str(run), 'check'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for line in (run / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert sha(run / name) == digest
    assert all(not path.stat().st_mode & 0o222 for path in [run, *run.rglob('*')])
    return {'rid': rid, 'verdict': verdict, 'manifest_sha256': sha(run / 'MANIFEST.sha256'),
        'all_hashes_match': True, 'all_read_only': True, 'history_check': json.loads(result.stdout)}


if __name__ == '__main__':
    results = []
    results.append(close('E2-R052a-night-20261009-v2', 'T11', 140, 'R052A_INDEPENDENT_TERMINAL_REVIEW.json',
        'runs/dev_R052', '.', 'result.json', 'not_met', 9))
    results.append(close('E2-R044-night-20261009', 'T10', 141, 'R044_INDEPENDENT_TERMINAL_REVIEW.json',
        'runs/dev_T10', 'ordinary/B1', 'failed_harness.json', 'failed_harness', 0))
    print(json.dumps(results), flush=True)
