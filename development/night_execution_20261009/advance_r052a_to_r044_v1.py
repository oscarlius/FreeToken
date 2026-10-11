"""Advance the authorized serial queue only after R052a's owned cleanup."""
import datetime
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
PREVIOUS = Path('/data2/_shared/runs/ft_rounds/E2-R052a-night-20261009-v2')
RID = 'E2-R044-night-20261009'
SOURCE = ROOT / 'runs/dev_night_tail_queue_20261009/source/runtime_v2/r044/r044_prepare_v6.py'
REVIEW = ROOT / 'runs/dev_T10/reviews/E2-R044-v7/review.json'
REVIEW_SHA = 'e8bb35c3c454cef4a6c32af373a347d4616db8ca8ad980c10cfa177063d02961'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def absent(pid, birth=None):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] == 'Z' or (birth is not None and int(fields[19]) != birth)
    except FileNotFoundError:
        return True


def main():
    previous_driver = json.loads((HERE / 'R052A_DRIVER_RECEIPT.json').read_text())
    while not absent(previous_driver['pid'], previous_driver['start_ticks']):
        time.sleep(30)
    cleanup = json.loads((PREVIOUS / 'owned_cleanup.json').read_text())
    assert cleanup['lock_released'] is True
    assert (PREVIOUS / 'result.json').is_file() or (PREVIOUS / 'failed_harness.json').is_file()
    owner = json.loads((PREVIOUS / 'owned_process.json').read_text())
    assert absent(owner['birth']['pid'], owner['birth']['start_ticks'])
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            assert fields[0] == 'Z' or int(fields[2]) != owner['birth']['pgid']
        except (FileNotFoundError, ProcessLookupError):
            pass
    assert not Path('/data2/_shared/gpu.lock').exists()
    assert not (ROOT / 'run/production.active.json').exists()
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    assert sha(REVIEW) == REVIEW_SHA
    review = json.loads(REVIEW.read_text())
    assert review['approved'] is True and review['verdict'] == 'PASS' and review['rid'] == RID
    for path, digest in review['source_sha256'].items():
        assert sha(path) == digest, path
    assert sha(review['file_dry_receipt']) == review['file_dry_receipt_sha256']
    assert not Path('/data2/_shared/runs/ft_rounds', RID).exists()
    receipt_path = HERE / 'R044_DRIVER_RECEIPT.json'
    assert not receipt_path.exists()
    argv = [str(ROOT / 'venv/bin/python'), '-B', '-u', str(SOURCE), '--run', '--worktree', str(ROOT / 'wt/e2base1-ordinary-rewind'), '--output-root', '/data2/_shared/runs/ft_rounds']
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    with (HERE / 'R044_DRIVER.log').open('xb') as log:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    fields = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()
    receipt = {'at': datetime.datetime.now().astimezone().isoformat(), 'epoch': time.time(), 'argv': argv, 'pid': process.pid, 'start_ticks': int(fields[19]), 'pgid': process.pid, 'source_sha256': sha(SOURCE), 'startup_review_sha256': sha(REVIEW), 'predecessor_cleanup_sha256': sha(PREVIOUS / 'owned_cleanup.json'), 'predecessor_terminal_review': 'pending; independent queue item', 'log': str(HERE / 'R044_DRIVER.log')}
    with receipt_path.open('x') as stream:
        json.dump(receipt, stream, indent=2)
    receipt_path.chmod(0o444)
    with (HERE / 'COORDINATION_LOG.jsonl').open('a') as stream:
        stream.write(json.dumps({'at': receipt['at'], 'epoch': time.time(), 'event': 'R044_STARTED_AFTER_R052A_OWNED_CLEANUP', 'receipt': str(receipt_path), 'receipt_sha256': sha(receipt_path), 'R052a_terminal_review': 'pending'}) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
