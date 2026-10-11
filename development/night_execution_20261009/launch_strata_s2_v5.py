"""Root-only serial launcher for the admitted, bounded Strata arms."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = Path('/data2/Strata/r002-prep/night_execution_20261009')
SOURCE = PACKET / 'run_s2_v5.py'
PYTHON = '/data2/Strata/Strata/.venv/bin/python'
SHA = '00a190787319e62e0e5dc5354a501e6aa6de331feed6ffd3097b04dab684e2f6'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arm', choices=['S2'])
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
    admission = PACKET / ('ROOT_ADMISSION_' + args.arm + '_V5.json')
    assert not admission.stat().st_mode & 0o222
    approval = json.loads(admission.read_text())
    assert approval['admit'] is True and approval['arm'] == args.arm
    if args.arm == 'S2':
        terminal = json.loads((PACKET / 'raw-runs/v3-S1/terminal.json').read_text())
        recovery_path = PACKET / 'S1_CLEANUP_RECOVERY.json'
        recovery = json.loads(recovery_path.read_text())
        assert digest(recovery_path) == '073f72f4c4ca13e9d5c896272cf9cebf5e6615c9ea554bec4052f6efaf56eb70'
        assert recovery['cleanup_ok'] and recovery['exact_owned_lock_released']
        assert recovery['original_terminal_sha256'] == digest(PACKET / 'raw-runs/v3-S1/terminal.json')
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
