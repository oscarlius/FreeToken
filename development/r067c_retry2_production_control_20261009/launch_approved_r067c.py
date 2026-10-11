"""Root launch gate; no automatic retry and no production stop in this entry."""
from pathlib import Path
import fcntl
import hashlib
import json
import subprocess
import time

HERE = Path(__file__).resolve().parent
PACKET = Path('/data2/FreeToken/development/r067c_retry2_short_tail_v1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_attempt(events, rid, prior_terminal=None):
    attempts = [x for x in events if x['event'] == 'attempt_reserved']
    assert all(x['rid'] != rid for x in attempts), 'duplicate attempt'
    assert len(attempts) < 3, 'two tooling retries already consumed'
    if attempts:
        assert prior_terminal and prior_terminal['verdict'] == 'failed_harness', 'only tooling failure is retryable'
        assert prior_terminal['rid'] == attempts[-1]['rid']
    else:
        assert prior_terminal is None
    return len(attempts)


def main():
    admit = json.loads((PACKET / 'RETRY2_ROOT_STARTUP_ADMISSION.json').read_text())
    assert admit['approved'] and admit['scope']['services_max'] == 10
    assert sha(__file__) == admit['launch_helper_sha256']
    assert admit['scope']['generation_calls_max'] == 14
    assert sha(admit['root_preflight_path']) == admit['root_preflight_sha256']
    assert sha(admit['independent_review_path']) == admit['independent_review_sha256']
    assert json.loads(Path(admit['independent_review_path']).read_text())['verdict'] == 'PASS'
    assert sha(admit['prepared_runner_packet_path']) == admit['prepared_runner_packet_sha256']
    packet = json.loads(Path(admit['prepared_runner_packet_path']).read_text())
    admission_sha = sha(PACKET / 'RETRY2_ROOT_STARTUP_ADMISSION.json')
    child = packet['child_source'].replace('__ADMISSION_SHA256__', admission_sha)
    parent = packet['parent_tail'].replace('__ADMISSION_SHA256__', admission_sha)
    assert '__ADMISSION_SHA256__' not in child + parent
    controller = ('import ast,hashlib,importlib.util,json,os,sys,time\nfrom pathlib import Path\n'
                  + 'CHILD=' + repr(child) + '\n' + parent)
    __import__('ast').parse(controller)
    assert not Path('/data2/FreeToken/run/production.active.json').exists()
    assert not Path('/data2/_shared/gpu.lock').exists()
    ledger = Path('/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl')
    with ledger.open('a+', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        events = [json.loads(line) for line in f if line.strip()]
        prior_path = admit.get('prior_terminal_path')
        prior = json.loads(Path(prior_path).read_text()) if prior_path else None
        retry = validate_attempt(events, admit['rid'], prior)
        event = {'event': 'attempt_reserved', 'rid': admit['rid'], 'retry_index': retry,
                 'admission_sha256': sha(PACKET / 'RETRY2_ROOT_STARTUP_ADMISSION.json'),
                 'prior_terminal_sha256': sha(prior_path) if prior_path else None, 'at': time.time()}
        f.seek(0, 2)
        f.write(json.dumps(event) + '\n')
        f.flush()
        __import__('os').fsync(f.fileno())
    controller_path = HERE / 'RETRY2_SEALED_CONTROLLER.py'
    with controller_path.open('x', encoding='utf-8') as f:
        f.write(controller)
    with (HERE / 'RETRY2_SEALED_CONTROLLER_RECEIPT.json').open('x', encoding='utf-8') as f:
        json.dump({'controller_sha256': sha(controller_path), 'admission_sha256': admission_sha,
                   'prepared_packet_sha256': admit['prepared_runner_packet_sha256'], 'at': time.time()}, f)
    return subprocess.call(['/data2/FreeToken/venv/bin/python', '-u', str(controller_path)])


if __name__ == '__main__':
    raise SystemExit(main())
