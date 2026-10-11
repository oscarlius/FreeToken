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

from release_config import ROOT, HOST, MODES, environment, serve_argv, environment_projection
from worktree_checks import validate_worktree

ACTIVE = ROOT / 'run/production.active.json'
QUARANTINE = ROOT / 'run/production.cleanup_failed.json'
HERE = Path(__file__).resolve().parent
BINARY_MANIFEST = HERE / 'binary_manifest.json'


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


def resource_snapshot(timeout=5):
    deadline = time.monotonic() + timeout
    ports = subprocess.check_output(
        ['ss', '-H', '-ltn', '( sport = :8095 or sport = :8096 )'], text=True, timeout=timeout)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Resource snapshot exhausted its deadline')
    processes = subprocess.check_output([
        'nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
        text=True, timeout=remaining)
    return {'ports': ports.strip(), 'compute_pids': processes.strip()}


def resources_released(timeout=60):
    """Wait at most 60 seconds, including command execution and sleeps."""
    if not 0 < timeout <= 60:
        raise ValueError('Resource release timeout must be within (0, 60]')
    deadline = time.monotonic() + timeout
    last = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('Resource release deadline exceeded: ' + str(last))
        try:
            last = resource_snapshot(min(5, remaining))
            if not last['ports'] and not last['compute_pids']:
                return last
        except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
            last = {'error': type(exc).__name__ + ': ' + str(exc)}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('Resource release deadline exceeded: ' + str(last))
        time.sleep(min(1, remaining))


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
    deadline = time.monotonic() + 220
    while time.monotonic() < deadline:
        now = d07.process_identity(state['supervisor']['pid'])
        if now is None or now.get('state') == 'Z' or now.get('start_ticks') != state['supervisor']['start_ticks']:
            try:
                snapshot = resource_snapshot()
                if snapshot['ports'] or snapshot['compute_pids']:
                    raise RuntimeError('Resources still occupied')
            except (RuntimeError, OSError, subprocess.SubprocessError, TimeoutError):
                pass
            else:
                if QUARANTINE.exists():
                    raise RuntimeError('Owned metadata released but cleanup quarantined; no rollback startup')
                if not d07.LOCK.exists() and not ACTIVE.exists():
                    return
        time.sleep(.2)
    raise RuntimeError('Stop exceeded 220s; inspect cleanup/alerts; do not start rollback')


def start(mode, approval, run_dir):
    if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
        raise RuntimeError('Start must run in its own setsid supervisor session')
    d07 = helpers()
    worktree, commit, _, _ = MODES[mode]
    if run_dir.parent != ROOT / 'runs/production' or run_dir.is_symlink():
        raise RuntimeError('Each deployment needs a new direct production run directory')
    if ACTIVE.exists() or ACTIVE.is_symlink():
        raise RuntimeError('Existing active PID record must be reconciled before startup')
    if QUARANTINE.exists() or QUARANTINE.is_symlink():
        raise RuntimeError('Unresolved cleanup quarantine blocks startup')
    manifest = json.loads(BINARY_MANIFEST.read_text(encoding='utf-8'))
    worktree_receipt = validate_worktree(worktree, commit, manifest, mode)
    run_dir.mkdir()  # must not reuse an earlier service generation
    exclusive(run_dir / 'worktree_receipt.json', worktree_receipt)
    owner = None
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
        if stopping:
            return
        owner = d07.take_d07_gpu_lock('production:' + mode + ':' + approval, 0)
        d07.load_owned_lifecycle()  # validate cleanup before creating a child
        d07.require_gpu_idle()
        resources_released()
        if stopping:
            return
        with (run_dir / 'serve.log').open('xb') as log:
            process = subprocess.Popen(serve_argv(mode), cwd=run_dir, env=environment(mode),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
        identity = d07.process_identity(process.pid)
        if identity is None:
            raise RuntimeError('Service exited before PID/birth binding')
        state = {'mode': mode, 'approval_id': approval, 'run_dir': str(run_dir),
                 'commit': commit, 'worktree': str(worktree), 'argv': serve_argv(mode),
                 'worktree_receipt': str(run_dir / 'worktree_receipt.json'),
                 'supervisor': d07.process_identity(os.getpid()), 'service': identity,
                 'gpu_owner': owner, 'restart': 'no outer restart', 'host': HOST,
                 'log': str(run_dir / 'serve.log'), 'stop_TERM_seconds': 120,
                 'stop_KILL_seconds': 30, 'at': time.time()}
        with (run_dir / 'monitor.log').open('xb') as monitor_log:
            monitor = subprocess.Popen([str(ROOT / 'venv/bin/python'), str(HERE / 'monitor_health.py'),
                '--run-dir', str(run_dir), '--supervisor', json.dumps(state['supervisor'])],
                cwd=run_dir, env=environment(mode), stdin=subprocess.DEVNULL,
                stdout=monitor_log, stderr=subprocess.STDOUT, start_new_session=True)
        state['monitor'] = d07.process_identity(monitor.pid)
        exclusive(run_dir / 'owner.json', state)
        exclusive(ACTIVE, state)
        record = ACTIVE.read_bytes()
        while process.poll() is None and not stopping:
            time.sleep(.2)
    finally:
        errors = []
        released = process is None
        try:
            if process is not None:
                try:
                    d07.load_owned_lifecycle().stop_owned_process(process, 120, 30)
                except BaseException as exc:
                    errors.append('owned child stop: ' + repr(exc))
                try:
                    resources_released()
                    released = True
                except BaseException as exc:
                    errors.append('resource release: ' + repr(exc))
        finally:
            try:
                if owner is not None:
                    d07.release_d07_gpu_lock(owner)
            except BaseException as exc:
                errors.append('owned lock release: ' + repr(exc))
            finally:
                try:
                    if record is not None:
                        if ACTIVE.is_symlink() or ACTIVE.read_bytes() != record:
                            raise RuntimeError('Active record replaced; never delete foreign ownership')
                        ACTIVE.unlink()
                except BaseException as exc:
                    errors.append('owned active cleanup: ' + repr(exc))
                finally:
                    for sig, handler in old_handlers.items():
                        signal.signal(sig, handler)
        status = {'at': time.time(), 'resources_released': released, 'errors': errors,
                  'supervisor_exit': True, 'approval_id': approval}
        from monitor_health import write_alert
        write_alert(run_dir, 'supervisor_exit', status)
        exclusive(run_dir / 'stopped.json', status)
        if errors:
            exclusive(QUARANTINE, status)
            raise RuntimeError('Cleanup failed; owned metadata cleanup attempted; quarantined: ' + repr(errors))


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
                         'environment': environment_projection(environment(args.mode)),
                         'worktree': str(MODES[args.mode][0]), 'starts_service': False}, indent=2))
    elif args.stop:
        stop(approval_id(args.approval_id))
    else:
        if args.run_dir is None:
            parser.error('--start requires --run-dir')
        start(args.mode, approval_id(args.approval_id), args.run_dir)


if __name__ == '__main__':
    main()
