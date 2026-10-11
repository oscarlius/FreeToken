"""Launch one leader-assigned E2 measurement batch after an inert preflight."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys


ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
BATCHES = ROOT / 'runs/plan_batches'
PY = str(ROOT / 'venv/bin/python')
ASSIGNMENTS = {
    'T03': ('E2-R008', 't03_runner.py', []),
    'T04': ('E2-R002', 'state_test_runner.py', ['--card', 'T04']),
    'T07': ('E2-R003', 't07_runner.py', []),
    'T08-P1': ('E2-R009', 't08_runner.py', ['--phase', 'P1']),
    'T08-P2': ('E2-R009-p64k', 't08_runner.py', ['--phase', 'P2']),
    'T09': ('E2-R010', 't09_runner.py', []),
    'T10': ('E2-R006', 'state_test_runner.py', ['--card', 'T10']),
    'T11': ('E2-R011', 'state_test_runner.py', ['--card', 'T11']),
}


def next_batch(root):
    numbers = [int(match.group(1)) for path in root.iterdir()
               if (match := re.fullmatch(r'batch(\d+)\.log', path.name))]
    if not numbers:
        raise ValueError('existing batch ledger is required')
    return max(numbers) + 1


def launch(card):
    rid, filename, extra = ASSIGNMENTS[card]
    if (ROUNDS / rid).exists():
        raise ValueError(f'assigned round already exists: {rid}')
    batch = next_batch(ROUNDS)
    runner = BATCHES / filename
    subprocess.run([PY, str(runner), '--self-test'], check=True)
    argv = [PY, '-u', str(runner), '--rid', rid, '--batch', str(batch), *extra]
    subprocess.run(argv, check=True)
    # Preflight is complete. Freeze this exact batch identity before creating it.
    if next_batch(ROUNDS) != batch or (ROUNDS / rid).exists():
        raise ValueError('batch ledger or round identity changed during preflight')
    process, script, log = reserve_and_launch(batch, rid, argv)
    print(json.dumps({'card': card, 'rid': rid, 'batch': batch, 'batch_pid': process.pid,
                      'batch_log': str(log), 'runner_sha256': hashlib.sha256(runner.read_bytes()).hexdigest(),
                      'wrapper_sha256': hashlib.sha256(script.read_bytes()).hexdigest()}), flush=True)


def reserve_and_launch(batch, rid, argv):
    script = BATCHES / f'batch{batch}_{rid}_python.sh'
    log = ROUNDS / f'batch{batch}.log'
    # The ledger entry is the exclusive reservation. A losing launcher creates no wrapper.
    with log.open('x') as out:
        try:
            with script.open('x', encoding='utf-8', newline='\n') as wrapper:
                wrapper.write('#!/bin/bash\nset -euo pipefail\nexec ' + shlex.join([*argv, '--run']) + '\n')
            subprocess.run(['bash', '-n', str(script)], check=True)
            process = subprocess.Popen(['bash', str(script)], stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        except BaseException as exc:
            # This batch number remains spent; preserve the exact launch failure for review.
            out.write(json.dumps({'state': 'launch_failed', 'rid': rid, 'batch': batch,
                                  'wrapper': str(script), 'error': repr(exc)}) + '\n')
            raise
    return process, script, log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--card', choices=ASSIGNMENTS)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ('batch9.log', 'batch26.log', 'batch2.log', 'batch999.log.tmp'):
                (directory / name).touch()
            assert next_batch(directory) == 27
            batches = directory / 'scripts'; batches.mkdir()
            with patch.dict(reserve_and_launch.__globals__, {'ROUNDS': directory, 'BATCHES': batches}):
                with patch.object(subprocess, 'run'), patch.object(subprocess, 'Popen', side_effect=OSError('injected')):
                    try:
                        reserve_and_launch(27, 'E2-R001', ['python', 'runner.py'])
                    except OSError:
                        pass
                    else:
                        raise AssertionError('Popen failure swallowed')
                assert 'launch_failed' in (directory / 'batch27.log').read_text()
                try:
                    reserve_and_launch(27, 'E2-R002', ['python', 'runner.py'])
                except FileExistsError:
                    pass
                else:
                    raise AssertionError('occupied batch reservation accepted')
                assert not (batches / 'batch27_E2-R002_python.sh').exists()
        assert len({value[0] for value in ASSIGNMENTS.values()}) == 8
        print('E2 LAUNCH SELFTEST PASS: exact assignments, atomic reservation, retained launch failure')
        return
    if sys.platform != 'linux' or not args.card:
        parser.error('Linux test host and one assigned --card are required')
    launch(args.card)


if __name__ == '__main__':
    main()
