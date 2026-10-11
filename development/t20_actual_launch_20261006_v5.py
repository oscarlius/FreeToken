"""Actual queued R040 launcher using the existing atomic owned-process protocol."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
STAGE = ROOT / 'runs/dev_D16/t20_startup_cpu_5deba0293ed3'
SOURCE = STAGE / 'source_tools'
CPU_SHA = '0bdee2876a4c66957e4a99c1713c7f901055a7443b78b2d9fc34e5bd5db94461'
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
PRIOR = 'E2-R041-gate-D17'
RID = 'E2-R040'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def argv_for(batch, options):
    """One complete T20 command; the owned allocator appends --run."""
    argv = [str(ROOT / 'venv/bin/python'), '-u', str(SOURCE / 't17_continuation_runner_v2.py'),
            '--run-kind', 't20', '--rid', RID, '--batch', str(batch),
            '--realinput28', str(SOURCE / 'realinput_28.json'),
            '--candidate-worktree', str(ROOT / 'wt/e2base1-ordinary-rewind'),
            '--candidate-sha', CANDIDATE, '--parent-sha', PARENT,
            '--cases', 't20-sample4', '--envelope-cases', 'sample4', '--t20-full',
            '--cpu-report', str(STAGE / 'startup_cpu_report.json'), '--source-root', str(SOURCE),
            '--rounds', str(ROUNDS), '--directory', str(ROUNDS / RID),
            '--prior-t16-rid', PRIOR, '--prior-t16-batch', '68',
            '--preflight-artifact', str(ROOT / f'runs/dev_D17/t20_preflight_batch{batch}.json'),
            '--r041-round', str(ROUNDS / PRIOR),
            '--accepted-t17-path', str(ROUNDS / 'E2-R038/round.json'),
            '--accepted-t17-review', str(ROUNDS / 'E2-R038/combined_review.json'),
            '--expected-tag', 'E2-base.1@0aa23431', '--expected-d17-commit', CANDIDATE,
            '--expected-d17-worktree', str(ROOT / 'wt/e2base1-ordinary-rewind')]
    for key in ('source_review', 'source_review_sha256', 'd16_source_review', 'd16_source_review_sha256',
                'r041_independent_review', 'caller_ir_sha256', 'closure_binding'):
        argv += ['--' + key.replace('_', '-'), str(getattr(options, key))]
    for key, name in (('expected_gate_case_sha256', 'd17_gate_case.py'),
                      ('expected_artifacts_sha256', 't17_d14_artifacts.py'),
                      ('expected_t16_runner_sha256', 't16_full_tail_base_runner.py'),
                      ('expected_parser_sha256', 'serve_args_diff.py'),
                      ('expected_d04_checker_sha256', 't17_continuation_runner.py'),
                      ('expected_verifier_sha256', 't20_r041_sample4_closure.py')):
        # Parser and D04 are archived dependencies; don't hash live host tools.
        path = SOURCE / name
        if not path.is_file():
            raise ValueError('required frozen T20 helper missing: ' + name)
        argv += ['--' + key.replace('_', '-'), sha(path)]
    return argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source_review', 'source_review_sha256', 'd16_source_review', 'd16_source_review_sha256',
                'r041_independent_review', 'caller_ir_sha256', 'closure_binding'):
        parser.add_argument('--' + key.replace('_', '-'), required=True)
    parser.add_argument('--run', action='store_true')
    options = parser.parse_args()
    closed = ROUNDS / PRIOR / 'round.json'
    if not closed.is_file() or json.loads(closed.read_text()).get('verdict') != 'kept':
        if options.run:
            raise ValueError('R041 canonical D04 kept prerequisite is not available')
        print(json.dumps({'state': 'awaiting_R041_D04', 'admitted': False, 'gpu_started': False}))
        return
    if sha(STAGE / 'startup_cpu_report.json') != CPU_SHA:
        raise ValueError('actual T20 CPU source package differs')
    for key in ('source_review_sha256', 'd16_source_review_sha256', 'caller_ir_sha256'):
        if re.fullmatch('[0-9a-f]{64}', getattr(options, key)) is None:
            raise ValueError('full caller-pinned review SHA required: ' + key)
    # This is an owned startup protocol from the CPU-tested immutable package.
    sys.path.insert(0, str(SOURCE))
    owned = module('actual_t20_owned_launch', SOURCE / 't17_owned_launch_protocol.py')
    helper = owned.verified_module(ROOT / 'runs/plan_batches/e2_launch.py', owned.HELPER_SHA,
                                   'actual_t20_atomic_launch')
    batch = helper.next_batch(ROUNDS)
    argv = argv_for(batch, options)
    if not options.run:
        print(json.dumps({'state': 'parameters_prepared', 'batch_advisory': batch,
                          'argv': argv + ['--run'], 'admitted': False, 'gpu_started': False}))
        return
    if (ROUNDS / RID).exists() or Path('/data2/_shared/gpu.lock').exists():
        raise ValueError('R040 output or another GPU owner already exists')
    memory = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used',
                                     '--format=csv,noheader,nounits'], text=True)
    if not memory.strip() or any(int(row) >= 1000 for row in memory.splitlines()):
        raise ValueError('GPU is not idle for its next queued owner')
    for key in list(os.environ):
        if key.startswith('FT_') or key == 'PYTHONPATH':
            os.environ.pop(key)
    os.environ.update(PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='0')
    receipt_path = ROOT / f'runs/dev_D17/launch_E2-R040_batch{batch}.json'
    packet = {'schema': 'ft_t20_actual_launch/v1', 'state': 'reserved', 'rid': RID,
              'batch': batch, 'card': 'T20', 'candidate_commit': CANDIDATE,
              'parent_commit': PARENT, 'cpu_report_sha256': CPU_SHA,
              'r041_round_sha256': sha(closed), 'launcher_sha256': sha(__file__),
              'atomic_helper_sha256': owned.HELPER_SHA, 'argv': argv + ['--run'],
              'model_admitted': False}
    receipt = owned.reserve_process(helper, batch, RID, argv, receipt_path, packet)
    pid = receipt['batch_pid']
    ticks = int((Path('/proc') / str(pid) / 'stat').read_text().rpartition(') ')[2].split()[19])
    if ticks <= 0 or os.getpgid(pid) != pid:
        raise ValueError('reserved controller birth identity differs')
    receipt.update(batch_start_ticks=ticks, batch_execution_id=f'{pid}:{ticks}')
    identity = receipt_path.stat()
    owned.publish_receipt(receipt_path, (identity.st_dev, identity.st_ino), receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
