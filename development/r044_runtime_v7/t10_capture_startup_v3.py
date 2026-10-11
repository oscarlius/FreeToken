"""T10 terminal-cap capture with controlled worker shutdown; no pause/trace."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import sys
import time


def worker_run_scheduler(args, ack_queue):
    from equiv_suite import service_capture_startup as capture
    from freetoken.scheduler import Scheduler
    from t10_capture_startup import install_terminal_cap
    if any(os.environ.get(key) not in (None, '', '0')
           for key in ('FT_DEV_ROUTE_TRACE', 'FT_DEV_PAUSE_ENDPOINT')):
        raise RuntimeError('T10 requires ordinary transport with route/pause disabled')
    output = Path(os.environ['FT_T10_WORKER_SHUTDOWN'])
    if output.is_symlink() or output.exists():
        raise RuntimeError('T10 worker shutdown output exists')
    original_install = capture.install_from_env
    original_run = Scheduler.run_forever
    previous = signal.getsignal(signal.SIGTERM)
    started = False
    shutdown_requested = False

    def install(engine):
        adapter = original_install(engine)
        return None if adapter is None else install_terminal_cap(adapter)

    def run(scheduler, *positional, **keywords):
        nonlocal started
        started = True
        return original_run(scheduler, *positional, **keywords)

    def terminate(signum, frame):
        nonlocal shutdown_requested
        if started:
            if not shutdown_requested:
                shutdown_requested = True
                raise KeyboardInterrupt
            return
        raise RuntimeError('T10 stopped before scheduler loop')

    capture.install_from_env = install
    Scheduler.run_forever = run
    signal.signal(signal.SIGTERM, terminate)
    status, error = 'complete', None
    try:
        return capture.run_scheduler(args, ack_queue)
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        capture.install_from_env = original_install
        Scheduler.run_forever = original_run
        row = {'schema': 'ft_t10_worker_shutdown/v3', 'status': status,
               'error': error, 'pid': os.getpid(), 'scheduler_run_started': started,
               'time_ns': time.time_ns()}
        stat = Path(f'/proc/{os.getpid()}/stat')
        if stat.is_file():
            row['start_ticks'] = int(stat.read_text().rpartition(') ')[2].split()[19])
        try:
            with output.open('x', encoding='utf-8') as stream:
                stream.write(json.dumps(row, sort_keys=True) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            signal.signal(signal.SIGTERM, previous)


def main(argv=None):
    directory = str(Path(__file__).resolve().parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    inherited = os.environ.get('PYTHONPATH', '')
    os.environ['PYTHONPATH'] = directory + (os.pathsep + inherited if inherited else '')
    stable = __import__('t10_capture_startup_v3')
    from freetoken.server import launch
    launch._run_scheduler = stable.worker_run_scheduler
    from freetoken.cli import main as ft_main
    sys.argv = ['ft', *(sys.argv[1:] if argv is None else argv)]
    return ft_main()


if __name__ == '__main__':
    raise SystemExit(main())
