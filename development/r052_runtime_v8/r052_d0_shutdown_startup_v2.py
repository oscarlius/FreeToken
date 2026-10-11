"""R052-only SIGTERM bridge to the unchanged scheduler's D0 shutdown path."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import sys
import time


def worker_run_scheduler(args, ack_queue):
    from freetoken.server.launch import _run_scheduler as original
    from freetoken.scheduler import Scheduler
    if original is worker_run_scheduler:
        raise RuntimeError('R052 worker target must be re-imported by spawn')
    if os.environ.get('FT_DEV_D0') != '1' or any(os.environ.get(key) not in (None, '', '0')
                                               for key in ('FT_DEV_ROUTE_TRACE', 'FT_DEV_PAUSE_ENDPOINT')):
        raise RuntimeError('R052 requires D0 with route and pause disabled')
    output = Path(os.environ['FT_R052_WORKER_SHUTDOWN'])
    if output.is_symlink() or output.exists():
        raise RuntimeError('R052 worker shutdown output already exists')
    started = False
    shutdown_requested = False
    run_forever = Scheduler.run_forever
    previous = signal.getsignal(signal.SIGTERM)

    def observed_run(scheduler, *positional, **keywords):
        nonlocal started
        started = True
        return run_forever(scheduler, *positional, **keywords)

    def terminate(signum, frame):
        nonlocal shutdown_requested
        if started:
            if not shutdown_requested:
                shutdown_requested = True
                raise KeyboardInterrupt
            return
        raise RuntimeError('R052 stopped before scheduler entered its loop')

    Scheduler.run_forever = observed_run
    signal.signal(signal.SIGTERM, terminate)
    status, error = 'complete', None
    try:
        return original(args, ack_queue)
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        Scheduler.run_forever = run_forever
        row = {'schema': 'ft_r052_worker_shutdown/v1', 'status': status, 'error': error,
               'pid': os.getpid(), 'scheduler_run_started': started, 'time_ns': time.time_ns()}
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
    stable = __import__('r052_d0_shutdown_startup_v2')
    from freetoken.server import launch
    launch._run_scheduler = stable.worker_run_scheduler
    from freetoken.cli import main as ft_main
    sys.argv = ['ft', *(sys.argv[1:] if argv is None else argv)]
    return ft_main()


if __name__ == '__main__':
    raise SystemExit(main())
