"""Close the failed original R067c using existing D04 append/read-only tools."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess

HERE = Path(__file__).resolve().parent
PACKET = Path('/data2/FreeToken/development/r067c_short_tail_v1')
RID = 'E2-R067c-d20-short-tail'
RAW = Path('/data2/FreeToken/runs/dev_R067') / RID
ROUND = Path('/data2/_shared/runs/ft_rounds') / RID
PY = '/data2/FreeToken/venv/bin/python'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same_birth(item):
    try:
        fields = Path(f"/proc/{item['pid']}/stat").read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and int(fields[19]) == item['start_ticks']
    except FileNotFoundError:
        return False


def main():
    terminal = json.loads((RAW / 'terminal.json').read_text())
    assert terminal['verdict'] == 'failed_harness' and terminal['batch'] == 135
    assert terminal['actual_services'] == terminal['actual_generation_calls'] == 1
    assert not terminal['cleanup_errors'] and terminal['GPU_lock_released']
    assert not terminal['cells'] and not terminal['requests']
    owner = json.loads((RAW / 'services/hot_p8192/owner.json').read_text())
    assert not same_birth(owner['pid_identity']) and not same_birth(owner['GPU_owner'])
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try:
                fields = (p / 'stat').read_text().rsplit(')', 1)[1].split()
                assert fields[0] == 'Z' or int(fields[2]) != owner['pid_identity']['pgid'], 'old test group remains'
            except (FileNotFoundError, ProcessLookupError):
                pass
    for port in (28390, 28391):
        with socket.socket() as s:
            s.bind(('0.0.0.0', port))
    # Production restoration has priority. Its new GPU ownership is retained and recorded.
    active = json.loads(Path('/data2/FreeToken/run/production.active.json').read_text())
    assert active['approval_id'] == 'RESTORE481-E2-R067c-20261009-01'
    preflight = json.loads((HERE / 'EXECUTION_TIME_PREFLIGHT.json').read_text())
    assert not preflight['compute_pids'].strip() and not preflight['production_listeners'].strip()
    assert all(int(x) < 1000 for x in preflight['GPU_memory_mib'].splitlines())
    review = json.loads((PACKET / 'R067C_INDEPENDENT_TERMINAL_REVIEW.json').read_text())
    assert review['verdict'] == 'failed_harness' and review['actual_generation_calls'] == 1
    for name, item in json.loads((PACKET / 'R067C_ALL_REMOTE_RAW_FILES_MANIFEST.json').read_text())['files'].items():
        assert sha(RAW / name) == item['sha256'], name
    assert not ROUND.exists()
    ROUND.mkdir()
    arms = {}
    for p in RAW.iterdir():
        if p.is_file():
            shutil.copy2(p, ROUND / p.name)
    for arm in (RAW / 'services').iterdir():
        assert arm.is_dir() and not arm.is_symlink()
        dest = ROUND / arm.name
        shutil.copytree(arm, dest)
        argv = json.loads((dest / 'argv.json').read_text())
        env = json.loads((dest / 'environment.json').read_text())
        (dest / 'SERVE_CMD.txt').write_text(shlex.join(argv) + '\n')
        (dest / 'ENV.txt').write_text(json.dumps(env, indent=2) + '\n')
        lines = [x for x in (dest / 'serve.log').read_text().splitlines() if x.startswith('ServerArgs(')]
        assert len(lines) == 1
        (dest / 'serve_args.txt').write_text(lines[0] + '\n')
        arms[arm.name] = {'raw_source': str(arm), 'actual_argv_sha256': hashlib.sha256(json.dumps(argv, separators=(',', ':')).encode()).hexdigest()}
    launch = RAW.parent / 'launch_E2-R067c-d20-short-tail_batch135.json'
    receipt = json.loads(launch.read_text())
    for source, name in ((launch, 'launch_receipt.json'), (Path(receipt['wrapper']), 'batch.sh'), (Path(receipt['batch_log']), 'batch135.log')):
        shutil.copy2(source, ROUND / name)
    binding = ROUND / 'startup_binding'
    binding.mkdir()
    for p in PACKET.iterdir():
        if p.is_file():
            shutil.copy2(p, binding / p.name)
    shutil.copytree(PACKET / 'tooling', binding / 'tooling', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(HERE / 'R067C_SEALED_CONTROLLER.py', binding / 'R067C_SEALED_CONTROLLER.py')
    shutil.copy2(HERE / 'R067C_SEALED_CONTROLLER_RECEIPT.json', binding / 'R067C_SEALED_CONTROLLER_RECEIPT.json')
    shutil.copy2(PACKET / 'R067C_INDEPENDENT_TERMINAL_REVIEW.json', ROUND / 'independent_review.json')
    cleanup = {'old_test_processes_absent': True, 'old_test_group_absent': True,
               'old_test_ports_bindable': [28390, 28391], 'terminal_cleanup_errors': [],
               'pre_restore_GPU_idle_proven': True, 'restored_production_owner': active,
               'production_not_stopped_for_closure': True}
    (ROUND / 'cleanup_readback.json').write_text(json.dumps(cleanup, indent=2) + '\n')
    document = {'schema': 'ft_round/v2', 'round_id': RID, 'card': 'R067', 'batch': 135,
                'retry_of': None, 'retry_index': 0, 'verdict': 'pending_review',
                'proposed_verdict': 'failed_harness', 'verdict_history': [], 'retractions': [],
                'serve': {'arms': arms}, 'base': {'commit': active['commit']},
                'experimental': {'candidate_commit': 'd50be0f8f84ab1105f788be8f1354773ad539b63'},
                'batch_logs': [{'path': receipt['batch_log'], 'sha256': sha(receipt['batch_log'])}],
                'raw_run': str(RAW), 'result_binding': {name: {'path': name, 'sha256': sha(ROUND / name)} for name in ('terminal.json', 'cleanup_readback.json')},
                'independent_review': {'path': 'independent_review.json', 'sha256': sha(ROUND / 'independent_review.json')},
                'actual_services': 1, 'actual_generation_calls': 1, 'cells_comparable': 0,
                'product_acceptance': False, 'retry_policy': {'maximum_tooling_retries': 2, 'used': 0}}
    (ROUND / 'round.json').write_text(json.dumps(document, indent=2) + '\n')
    closer = Path('/data2/FreeToken/runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py')
    assert sha(closer) == 'db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
    close = subprocess.run([PY, str(closer), RID, '--round-root', str(ROUND.parent)], capture_output=True, text=True)
    assert close.returncode == 0, close.stderr
    appender = '/data2/FreeToken/scripts/round_json_append.py'
    append = subprocess.run([PY, appender, str(ROUND), 'verdict', '--new', 'failed_harness',
             '--reason', 'Independent review confirms the seed request succeeded but the controller incorrectly summed the same sequence across two native prefill rows. One service and one seed call; no comparable cell or product conclusion. Owned cleanup completed and production restoration took priority.',
             '--evidence', str(ROUND / 'terminal.json'), str(ROUND / 'independent_review.json'), str(ROUND / 'cleanup_readback.json'), '--by', 'root'], capture_output=True, text=True)
    assert append.returncode == 0, append.stderr
    check = subprocess.run([PY, appender, str(ROUND), 'check'], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert sha(ROUND / name) == digest, name
    assert all(not p.stat().st_mode & 0o222 for p in [ROUND, *ROUND.rglob('*')])
    print(json.dumps({'formal_round': str(ROUND), 'D04': json.loads(close.stdout),
                     'append': json.loads(append.stdout), 'history_check': json.loads(check.stdout),
                     'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'), 'all_hashes_match': True,
                     'all_read_only': True, 'verdict': 'failed_harness'}))


if __name__ == '__main__':
    main()
