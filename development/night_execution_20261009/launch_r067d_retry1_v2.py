"""Root launch gate; no automatic retry and no production stop in this entry."""
from pathlib import Path
import fcntl
import hashlib
import json
import subprocess
import time
import os
import stat
import datetime

HERE = Path(__file__).resolve().parent
PACKET = Path('/data2/FreeToken/development/r067d_short_tail_retry1_20261010')
ATTEMPT_RIDS = ('E2-R067d-d20-short-tail-v1', 'E2-R067d-d20-short-tail-retry1', 'E2-R067d-d20-short-tail-retry2')


def sha(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), str(path)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_attempt(events, rid, prior_terminal=None):
    attempts = [x for x in events if x['event'] == 'attempt_reserved']
    assert len(attempts) < 3, 'two tooling retries already consumed'
    assert [x['rid'] for x in attempts] == list(ATTEMPT_RIDS[:len(attempts)]), 'foreign or reordered family attempt'
    assert rid == ATTEMPT_RIDS[len(attempts)], 'every attempt needs its own new formal RID'
    if attempts:
        assert prior_terminal and prior_terminal['verdict'] == 'failed_harness', 'only tooling failure is retryable'
        assert prior_terminal['rid'] == attempts[-1]['rid']
    else:
        assert prior_terminal is None
    return len(attempts)


def sealed_write(path, value, raw=False):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value if raw else json.dumps(value, indent=2))
        stream.flush(); os.fsync(stream.fileno())
    path.chmod(0o444)
    with path.open('rb') as stream: os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    assert now.hour < 6 or (now.hour == 6 and now.minute < 45)
    admit = json.loads((PACKET / 'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json').read_text())
    assert admit['approved'] and admit['scope']['services_max'] == 10
    assert sha(__file__) == admit['launch_helper_sha256']
    assert admit['scope']['generation_calls_max'] == 14
    assert sha(admit['root_preflight_path']) == admit['root_preflight_sha256']
    assert sha(admit['independent_review_path']) == admit['independent_review_sha256']
    assert json.loads(Path(admit['independent_review_path']).read_text())['verdict'] in ('PASS','CPU_PASS','CPU_APPROVE_CONDITIONAL_QUEUE_CLEANUP')
    assert sha(admit['prepared_runner_packet_path']) == admit['prepared_runner_packet_sha256']
    packet = json.loads(Path(admit['prepared_runner_packet_path']).read_text())
    admission_sha = sha(PACKET / 'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json')
    child = packet['child_source'].replace('__ADMISSION_SHA256__', admission_sha)
    parent = packet['parent_tail'].replace('__ADMISSION_SHA256__', admission_sha)
    assert '__ADMISSION_SHA256__' not in child + parent
    controller = ('import ast,hashlib,importlib.util,json,os,sys,time\nfrom pathlib import Path\n'
                  + 'CHILD=' + repr(child) + '\n' + parent)
    __import__('ast').parse(controller)
    window=json.loads((HERE/'R067D_RETRY1_MEASUREMENT_WINDOW_READY.json').read_text())
    assert window['ready'] and window['compilation_processes_absent']
    assert 0 <= time.time() - window['at_epoch'] < 120
    for path in ('/data2/FreeToken/run/production.active.json', '/data2/FreeToken/run/production.cleanup_failed.json', '/data2/_shared/gpu.lock'):
        assert not Path(path).exists() and not Path(path).is_symlink(), path
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    cleanup = admit['predecessor_cleanup']
    assert sha(cleanup['path']) == cleanup['sha256']
    assert json.loads(Path(cleanup['path']).read_text())['cleanup_ok']
    for path, digest in json.loads(Path(admit['root_preflight_path']).read_text())['bindings'].items():
        assert sha(path) == digest, path
    assert not Path('/data2/FreeToken/run/production.active.json').exists()
    assert not Path('/data2/_shared/gpu.lock').exists()
    ledger = Path('/data2/FreeToken/development/night_execution_20261009/R067D_ATTEMPT_LEDGER.jsonl')
    with ledger.open('a+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        events = [json.loads(line) for line in f if line.strip()]
        prior_path = admit.get('prior_terminal_path')
        prior = json.loads(Path(prior_path).read_text()) if prior_path else None
        retry = validate_attempt(events, admit['rid'], prior)
        event = {'event': 'attempt_reserved', 'rid': admit['rid'], 'retry_index': retry,
                 'admission_sha256': sha(PACKET / 'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json'),
                 'prior_terminal_sha256': sha(prior_path) if prior_path else None, 'at': time.time()}
        f.seek(0, 2)
        f.write(json.dumps(event) + '\n')
        f.flush()
        __import__('os').fsync(f.fileno())
    controller_path = HERE / (admit['rid'] + '_SEALED_CONTROLLER.py')
    sealed_write(controller_path, controller, raw=True)
    sealed_write(HERE / (admit['rid'] + '_SEALED_CONTROLLER_RECEIPT.json'), {'controller_sha256': sha(controller_path), 'admission_sha256': admission_sha,
        'prepared_packet_sha256': admit['prepared_runner_packet_sha256'], 'at': time.time()})
    return subprocess.call(['/data2/FreeToken/venv/bin/python', '-u', str(controller_path)])


if __name__ == '__main__':
    raise SystemExit(main())
