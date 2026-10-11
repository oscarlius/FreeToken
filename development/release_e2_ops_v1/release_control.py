"""Prepared setsid supervisor; --plan is inert. Starting needs actual approval.

Reuses D07's atomic GPU lock and owned process-group cleanup. There is no
automatic outer restart; the candidate's internal OOM worker recovery remains.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from release_config import ROOT, HOST, MODES, environment, serve_argv

ACTIVE = ROOT / 'run/production.active.json'
HERE = Path(__file__).resolve().parent


def helpers():
    path = HERE.parent / 'd07_g3g4_prepare.py'
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != 'c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0':
        raise RuntimeError('Pinned D07 lifecycle/lock helper differs')
    spec = importlib.util.spec_from_file_location('release_d07', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def approval_id(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', value or ''):
        raise ValueError('A recorded deployment/downtime approval ID is required')
    return value


def exclusive(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2)
        handle.write('\n')


def resources_released():
    ports = subprocess.check_output(
        ['ss', '-H', '-ltn', '( sport = :8095 or sport = :8096 )'], text=True)
    processes = subprocess.check_output([
        'nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True)
    if ports.strip() or processes.strip():
        raise RuntimeError('GPU compute applications or reserved ports remain; preserve owner lock')


def verify_identity(d07, wanted):
    current = d07.process_identity(wanted['pid'])
    if current is None or any(current.get(key) != wanted.get(key)
                              for key in ('pid', 'start_ticks', 'execution_id', 'pgid', 'session')):
        raise RuntimeError('Supervisor birth/group identity differs; do not signal')


def stop(approval):
    d07 = helpers()
    if ACTIVE.is_symlink():
        raise RuntimeError('Active record must be an ordinary owned file')
    blob = ACTIVE.read_bytes()
    state = json.loads(blob)
    verify_identity(d07, state['supervisor'])
    exclusive(Path(state['run_dir']) / ('stop_' + approval + '.json'), {
        'approval_id': approval, 'target': state['supervisor'], 'at': time.time()})
    os.kill(state['supervisor']['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 170
    while time.monotonic() < deadline:
        now = d07.process_identity(state['supervisor']['pid'])
        if now is None or now.get('state') == 'Z' or now.get('start_ticks') != state['supervisor']['start_ticks']:
            try:
                resources_released()
            except RuntimeError:
                pass
            else:
                if not d07.LOCK.exists() and not ACTIVE.exists():
                    return
        time.sleep(.2)
    raise RuntimeError('Stop exceeded 170s; preserve evidence/lock and escalate, do not start rollback')


def start(mode, approval, run_dir):
    if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
        raise RuntimeError('Start must run in its own setsid supervisor session')
    d07 = helpers()
    worktree, commit, _, _ = MODES[mode]
    if run_dir.parent != ROOT / 'runs/production' or run_dir.is_symlink():
        raise RuntimeError('Each deployment needs a new direct production run directory')
    if ACTIVE.exists() or ACTIVE.is_symlink():
        raise RuntimeError('Existing active PID record must be reconciled before startup')
    head = subprocess.check_output(['git', '-C', str(worktree), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(worktree), 'status', '--porcelain', '--untracked-files=all', '--ignored'], text=True)
    if head != commit or dirty:
        raise RuntimeError('Expected clean release/rollback commit differs')
    run_dir.mkdir()  # must not reuse an earlier service generation
    owner = d07.take_d07_gpu_lock('production:' + mode + ':' + approval, 0)
    process = None
    record = None
    stopping = False
    stop_signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    old_handlers = {sig: signal.getsignal(sig) for sig in stop_signals}

    def request_stop(*_):
        nonlocal stopping
        stopping = True

    for sig in stop_signals:
        signal.signal(sig, request_stop)
    try:
        d07.load_owned_lifecycle()  # validate cleanup before creating a child
        d07.require_gpu_idle()
        resources_released()
        with (run_dir / 'serve.log').open('xb') as log:
            process = subprocess.Popen(serve_argv(mode), cwd=worktree, env=environment(mode),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
        identity = d07.process_identity(process.pid)
        if identity is None:
            raise RuntimeError('Service exited before PID/birth binding')
        state = {'mode': mode, 'approval_id': approval, 'run_dir': str(run_dir),
                 'commit': commit, 'worktree': str(worktree), 'argv': serve_argv(mode),
                 'supervisor': d07.process_identity(os.getpid()), 'service': identity,
                 'gpu_owner': owner, 'restart': 'no outer restart', 'host': HOST,
                 'log': str(run_dir / 'serve.log'), 'stop_TERM_seconds': 120,
                 'stop_KILL_seconds': 30, 'at': time.time()}
        exclusive(run_dir / 'owner.json', state)
        exclusive(ACTIVE, state)
        record = ACTIVE.read_bytes()
        while process.poll() is None and not stopping:
            time.sleep(.2)
    finally:
        if process is not None:
            d07.load_owned_lifecycle().stop_owned_process(process, 120, 30)
            resources_released()
        if record is not None:
            if ACTIVE.is_symlink() or ACTIVE.read_bytes() != record:
                raise RuntimeError('Active PID record changed; refuse to unlink')
        d07.release_d07_gpu_lock(owner)
        if record is not None:
            ACTIVE.unlink()
        exclusive(run_dir / 'stopped.json', {'at': time.time(), 'resources_released': True})
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--plan', action='store_true')
    actions.add_argument('--start', action='store_true')
    actions.add_argument('--stop', action='store_true')
    parser.add_argument('--mode', choices=tuple(MODES), default='release')
    parser.add_argument('--approval-id')
    parser.add_argument('--run-dir', type=Path)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps({'mode': args.mode, 'argv': serve_argv(args.mode),
                         'worktree': str(MODES[args.mode][0]), 'starts_service': False}, indent=2))
    elif args.stop:
        stop(approval_id(args.approval_id))
    else:
        if args.run_dir is None:
            parser.error('--start requires --run-dir')
        start(args.mode, approval_id(args.approval_id), args.run_dir)


if __name__ == '__main__':
    main()
