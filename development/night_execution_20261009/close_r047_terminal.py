"""Seal the actual R047 result after the independent not_met judgement."""
import hashlib
import json
import shlex
import shutil
import socket
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RID = 'E2-R047-night-20261009'
ROUND = Path('/data2/_shared/runs/ft_rounds') / RID
PY = '/data2/FreeToken/venv/bin/python'
SHA = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def absent(pid, birth=None):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] == 'Z' or (birth is not None and int(fields[19]) != birth)
    except FileNotFoundError:
        return True


def main():
    result = json.loads((ROUND / 'result.json').read_text())
    cleanup = json.loads((ROUND / 'owned_cleanup.json').read_text())
    review_path = HERE / 'R047_INDEPENDENT_TERMINAL_REVIEW.json'
    review = json.loads(review_path.read_text())
    assert result['rid'] == cleanup['rid'] == RID
    assert result['batch'] == cleanup['batch'] == 139
    assert cleanup['lock_released'] is True and review['verdict'] == 'not_met'
    assert review['result_sha256'] == SHA(ROUND / 'result.json')
    assert review['cleanup_sha256'] == SHA(ROUND / 'owned_cleanup.json')
    assert len(result['arms']) == review['actualservices'] == 6
    assert review['calls'] == 24
    assert all(row['actual_successful_snapshots'] == 0 for row in result['arms'])
    assert not result['nonzero_coverage_claimed']
    assert not (ROUND / 'round.json').exists()
    assert not Path('/data2/_shared/gpu.lock').exists()
    assert not Path('/data2/FreeToken/run/production.active.json').exists()
    assert not subprocess.check_output(
        ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
        text=True).strip()
    pair = json.loads((ROUND / 'port_pair.json').read_text())
    sockets = []
    try:
        for key in ('api', 'tcpstore'):
            sock = socket.socket(); sockets.append(sock); sock.bind(('0.0.0.0', pair[key]))
    finally:
        for sock in sockets: sock.close()
    launch = Path('/data2/FreeToken/runs/dev_T03b') / f'launch_{RID}_batch139.json'
    receipt = json.loads(launch.read_text())
    assert absent(receipt['child']['pid'], receipt['child']['start_ticks'])
    arms = {}
    for row in result['arms']:
        name = row['arm']; arm = ROUND / name
        command = json.loads((arm / 'serve_argv.json').read_text())
        owner = json.loads((arm / 'owned_process.json').read_text())
        assert absent(owner['pid'])
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit(): continue
            try:
                stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
                assert stat[0] == 'Z' or int(stat[2]) != owner['pgid']
            except (FileNotFoundError, ProcessLookupError): pass
        assert len(list(arm.glob('positive_turn[0-2].json'))) == 3
        assert (arm / 'negative.json').is_file()
        lines = [line for line in (arm / 'serve.log').read_text().splitlines()
                 if line.startswith('ServerArgs(')]
        assert len(lines) == 1
        for filename, text in (
            ('SERVE_CMD.txt', shlex.join(command['argv']) + '\n'),
            ('ENV.txt', json.dumps(command['environment'], indent=2) + '\n'),
            ('serve_args.txt', lines[0] + '\n')):
            with (arm / filename).open('x') as stream: stream.write(text)
        arms[name] = {'argv_binding': name + '/serve_argv.json'}
    for source, name in ((launch, 'launch_receipt.json'),
                         (Path(receipt['wrapper']), 'batch.sh'),
                         (Path(receipt['batch_log']), 'batch139.log'),
                         (review_path, 'independent_review.json'),
                         (HERE / 'R047_INDEPENDENT_TERMINAL_REVIEW.md', 'independent_review.md')):
        shutil.copy2(source, ROUND / name)
    proof = {'test_children_absent': True, 'test_groups_absent': True,
             'api_tcpstore_ports_bindable': True, 'gpu_compute_processes_absent': True,
             'gpu_lock_absent': True, 'production_stopped_under_user_authority': True,
             'restore481_required_after_remaining_queue': True}
    with (ROUND / 'cleanup_readback.json').open('x') as stream:
        json.dump(proof, stream, indent=2); stream.write('\n')
    document = {'schema': 'ft_round/v2', 'round_id': RID, 'card': 'T03b', 'batch': 139,
                'retry_of': None, 'retry_index': 0, 'verdict': 'pending_review',
                'proposed_verdict': review['verdict'], 'verdict_history': [], 'retractions': [],
                'serve': {'arms': arms},
                'base': {'commit': result['candidate_commit']},
                'experimental': {'candidate_commit': result['candidate_commit']},
                'batch_logs': [{'path': receipt['batch_log'], 'sha256': SHA(receipt['batch_log'])}],
                'actual_services': 6, 'actual_generation_calls': 24,
                'coverage_status': result['coverage_status'], 'product_acceptance': False,
                'result_binding': {name: {'path': name, 'sha256': SHA(ROUND / name)}
                                   for name in ('result.json', 'owned_cleanup.json', 'cleanup_readback.json')},
                'independent_review': {'path': 'independent_review.json',
                                       'sha256': SHA(ROUND / 'independent_review.json')},
                'retry_policy': {'maximum_tooling_retries': 2, 'used': 0,
                                  'product_not_met_stops_this_round': True}}
    with (ROUND / 'round.json').open('x') as stream:
        json.dump(document, stream, indent=2); stream.write('\n')
    closer = Path('/data2/FreeToken/runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py')
    assert SHA(closer) == 'db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
    closed = subprocess.run([PY, str(closer), RID, '--round-root', str(ROUND.parent)],
                            capture_output=True, text=True)
    assert closed.returncode == 0, closed.stderr
    append = '/data2/FreeToken/scripts/round_json_append.py'
    verdict = subprocess.run([PY, append, str(ROUND), 'verdict', '--new', review['verdict'],
                              '--reason', review['summary'], '--evidence',
                              str(ROUND / 'result.json'), str(ROUND / 'independent_review.json'),
                              str(ROUND / 'cleanup_readback.json'), '--by', 'root'],
                             capture_output=True, text=True)
    assert verdict.returncode == 0, verdict.stderr
    check = subprocess.run([PY, append, str(ROUND), 'check'], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, filename = line.split('  ', 1)
        assert SHA(ROUND / filename) == digest, filename
    assert all(not p.stat().st_mode & 0o222 for p in [ROUND, *ROUND.rglob('*')])
    print(json.dumps({'formal_round': str(ROUND), 'verdict': review['verdict'],
                      'manifest_sha256': SHA(ROUND / 'MANIFEST.sha256'),
                      'D04': json.loads(closed.stdout), 'history_check': json.loads(check.stdout),
                      'all_hashes_match': True, 'all_read_only': True}))


if __name__ == '__main__': main()
