"""R040d Scheduler instance hook around the replacement native capture API."""
from __future__ import annotations

import logging
import os
import signal
from typing import Any

from r040d_d16_native_service_capture_v2 import ServiceCaptureAdapter, ServiceCaptureError, install_from_env


def _messages(value: object) -> list[object]:
    if isinstance(value, (list, tuple)):
        return [item for part in value for item in _messages(part)]
    data = getattr(value, "data", None)
    return _messages(data) if isinstance(data, list) else [value]


def install_scheduler_capture(scheduler: object, *, user_message_type: type | None = None,
                              detokenize_message_type: type | None = None,
                              adapter: ServiceCaptureAdapter | None = None) -> ServiceCaptureAdapter | None:
    """Install only on this Scheduler and return the attached R040d adapter."""
    if adapter is None:
        adapter = install_from_env(getattr(scheduler, "engine", None))
    elif not isinstance(adapter, ServiceCaptureAdapter):
        raise ServiceCaptureError("R040d scheduler hook needs a R040d adapter")
    if adapter is None:
        return None
    if user_message_type is None or detokenize_message_type is None:
        from freetoken.message import DetokenizeMsg, UserMsg
        user_message_type, detokenize_message_type = UserMsg, DetokenizeMsg
    process, send = getattr(scheduler, "_process_one_msg", None), getattr(scheduler, "send_result", None)
    prepare, shutdown = getattr(scheduler, "_prepare_batch", None), getattr(scheduler, "shutdown", None)
    if not callable(process) or not callable(send) or not callable(prepare) or not callable(shutdown):
        raise ServiceCaptureError("Scheduler has no process/send/prepare/shutdown interface")

    def process_wrapper(message: object):
        if isinstance(message, user_message_type):
            adapter.admit_user_msg(message)
        return process(message)

    def send_wrapper(reply: object):
        result = send(reply)
        for message in _messages(reply):
            if isinstance(message, detokenize_message_type):
                adapter.observe_detokenize(message)
        return result

    def prepare_wrapper(batch: object):
        # Scheduler owns preparation.  Observe the same batch that its later
        # ``Engine.forward_batch(batch, sample_args)`` will receive.
        result = prepare(batch)
        adapter.observe_prepared_batch(batch)
        return result

    def shutdown_wrapper():
        try:
            return shutdown()
        finally:
            # The normal worker lifecycle seals after owned shutdown, including
            # SIGTERM converted to KeyboardInterrupt by ``run_scheduler``.
            adapter.finish()

    scheduler._process_one_msg = process_wrapper
    scheduler.send_result = send_wrapper
    scheduler._prepare_batch = prepare_wrapper
    scheduler.shutdown = shutdown_wrapper
    return adapter


def install(scheduler: object) -> ServiceCaptureAdapter | None:
    """Compatibility entry point used by the native startup wrapper."""
    return install_scheduler_capture(scheduler)


def run_scheduler(args: Any, ack_queue: Any) -> None:
    """Drop-in 0aa worker launcher with R040d instance capture lifecycle."""
    from freetoken.server.launch import _detach_process_group, _report_startup_error
    if args.shell_mode:
        _detach_process_group()
    from freetoken.gpu_select import set_assigned_gpu
    targets = args.gpu_assigned or args.gpu or tuple(str(rank) for rank in range(args.tp_info.size))
    set_assigned_gpu(targets[args.tp_info.rank])
    import torch
    from freetoken.scheduler import Scheduler
    if args.tp_info.is_primary():
        from freetoken.utils.progress import set_progress_sink
        set_progress_sink(lambda desc, done, total: ack_queue.put(("progress", desc, done, total)))
    try:
        with torch.inference_mode():
            scheduler = Scheduler(args)
            if args.tp_info.is_primary():
                install_scheduler_capture(scheduler)
            scheduler.sync_all_ranks()
    except Exception as error:
        _report_startup_error(ack_queue, error)
        raise
    if args.tp_info.is_primary():
        ack_queue.put("Scheduler is ready")
        from freetoken.utils.progress import set_progress_sink
        set_progress_sink(None)
    if args.silent_output:
        logging.disable(logging.INFO)
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda _signum, _frame: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            # Seal even if a retained scheduler returns rather than raising.
            scheduler.shutdown()
        finally:
            signal.signal(signal.SIGTERM, previous)


def install_launcher() -> None:
    """Install the bounded worker replacement only when the capture env is on."""
    from freetoken.server import launch
    launch._run_scheduler = run_scheduler


def main(argv: list[str] | None = None) -> None:
    from freetoken.server import launch
    if os.environ.get("FT_D16_SERVICE_CAPTURE_DIR"):
        install_launcher()
    launch.launch_server(argv=argv)
