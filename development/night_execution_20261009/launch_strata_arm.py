"""Root-only serial launcher for the admitted, bounded Strata arms."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = Path('/data2/Strata/r002-prep/night_execution_20261009')
SOURCE = PACKET / 'run_s1_s2_v4.py'
PYTHON = '/data2/Strata/Strata/.venv/bin/python'
SHA = '504a1bcba3704776ae04cab8387c04c84e66f4237e3b0e67352e66c3144b9490'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arm', choices=['S1', 'S2'])
    args = parser.parse_args()
    prior = Path('/data2/_shared/runs/ft_rounds/E2-R047-night-20261009')
    cleanup = json.loads((prior / 'owned_cleanup.json').read_text())
    assert cleanup['lock_released'] is True
    assert (prior / 'result.json').exists() or (prior / 'failed_harness.json').exists()
    assert (prior / 'round.json').exists() and (prior / 'MANIFEST.sha256').exists()
    assert not prior.stat().st_mode & 0o222
    assert not Path('/data2/_shared/gpu.lock').exists()
    assert not Path('/data2/FreeToken/run/production.active.json').exists()
    assert not subprocess.check_output(
        ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
        text=True).strip()
    assert digest(SOURCE) == SHA
    admission = PACKET / ('ROOT_ADMISSION_' + args.arm + '.json')
    assert not admission.stat().st_mode & 0o222
    approval = json.loads(admission.read_text())
    assert approval['admit'] is True and approval['arm'] == args.arm
    if args.arm == 'S2':
        terminal = json.loads((PACKET / 'raw-runs/v3-S1/terminal.json').read_text())
        assert terminal['cleanup_ok'] is True
    log_path = HERE / ('STRATA_' + args.arm + '_DRIVER.log')
    receipt_path = HERE / ('STRATA_' + args.arm + '_DRIVER_RECEIPT.json')
    assert not receipt_path.exists()
    command = [PYTHON, '-B', '-u', str(SOURCE), '--run', args.arm]
    with log_path.open('xb') as log:
        child = subprocess.Popen(command, cwd=PACKET, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    stat = Path('/proc/' + str(child.pid) + '/stat').read_text().rsplit(')', 1)[1].split()
    receipt = {'at': time.time(), 'arm': args.arm, 'argv': command,
               'source_sha256': digest(SOURCE), 'admission_sha256': digest(admission),
               'pid': child.pid, 'start_ticks': int(stat[19]), 'pgid': int(stat[2]),
               'r047_manifest_sha256': digest(prior / 'MANIFEST.sha256'),
               'log': str(log_path)}
    with receipt_path.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
