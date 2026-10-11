"""Standalone opt-in launcher for D16 service sampler capture.

Run with ``PYTHONPATH=python:scripts python scripts/equiv_suite/service_capture_startup.py``.
This module does not modify FreeToken source: it wraps one constructed Scheduler
instance only, and only when the capture environment is explicitly configured.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from equiv_suite.service_capture import ServiceCaptureAdapter, ServiceCaptureError, install_from_env


def _messages(value: object) -> list[object]:
    """Flatten only the service's list/Batch message containers."""
    if isinstance(value, (list, tuple)):
        result: list[object] = []
        for item in value:
            result.extend(_messages(item))
        return result
    data = getattr(value, "data", None)
    if isinstance(data, list):
        return _messages(data)
    return [value]


def _dev_d16_destination() -> None:
    raw = os.environ.get("FT_D16_SERVICE_CAPTURE_DIR", "")
    if "dev_D16" not in Path(raw).parts:
        raise ServiceCaptureError("FT_D16_SERVICE_CAPTURE_DIR must be inside an independent dev_D16 path")


def install_scheduler_capture(scheduler: object) -> ServiceCaptureAdapter | None:
    """Attach one already-constructed Scheduler without changing its class or queues."""
    if not os.environ.get("FT_D16_SERVICE_CAPTURE_DIR"):
        return None
    _dev_d16_destination()
    engine = getattr(scheduler, "engine", None)
    adapter = install_from_env(engine)
    if adapter is None:  # defensive: the preceding env check is intentionally exact
        return None
    try:
        from freetoken.message import DetokenizeMsg, UserMsg
    except ImportError as error:
        raise ServiceCaptureError("FreeToken message definitions are unavailable") from error
    original_process = getattr(scheduler, "_process_one_msg", None)
    original_send = getattr(scheduler, "send_result", None)
    original_shutdown = getattr(scheduler, "shutdown", None)
    original_schedule = getattr(scheduler, "_schedule_next_batch", None)
    if not callable(original_process) or not callable(original_send) or not callable(original_shutdown) or not callable(original_schedule):
        raise ServiceCaptureError("Scheduler instance lacks required message and shutdown methods")

    def process_wrapper(message: object):
        if isinstance(message, UserMsg):
            try:
                adapter.admit_user_msg(message)
            except Exception as error:  # diagnostics must not suppress the original scheduler call
                adapter.record_observer_error(f"UserMsg binding failed: {type(error).__name__}: {error}")
        return original_process(message)

    def send_wrapper(reply: object):
        # A returned send_result means the scheduler issued the physical delivery.  Do not
        # classify a native sampler event as delivery before this call has succeeded.
        try:
            result = original_send(reply)
        except BaseException as error:
            adapter.record_observer_error(f"send_result raised: {type(error).__name__}: {error}")
            raise
        for message in _messages(reply):
            if isinstance(message, DetokenizeMsg):
                try:
                    adapter.observe_detokenize(message)
                except Exception as error:  # delivery diagnostics never alter service output
                    adapter.record_observer_error(f"DetokenizeMsg observation failed: {type(error).__name__}: {error}")
        return result

    batch_observer_failed = False

    def schedule_wrapper():
        nonlocal batch_observer_failed
        # Native scheduling and preparation finish before the observer reads its result.
        # Therefore an observer fault cannot change the selected batch or scheduler return.
        result = original_schedule()
        if result is not None and not batch_observer_failed:
            try:
                adapter.observe_scheduler_batch(getattr(result, "batch", None))
            except Exception as error:
                # Do not retain one diagnostic error per later forward after a bounded
                # observer has exhausted its configured receipt budget.
                batch_observer_failed = True
                adapter.record_observer_error(f"Scheduler batch observation failed: {type(error).__name__}: {error}")
        return result

    def shutdown_wrapper():
        try:
            return original_shutdown()
        finally:
            # Shutdown/EOF is the only automatic seal point.  In particular, delivery of a
            # donor query never seals a multi-query capture before its later hit/query arrives.
            try:
                adapter.finalize()
            except Exception as error:  # retain diagnostic failed result; do not mask service shutdown
                adapter.record_observer_error(f"shutdown finalization failed: {type(error).__name__}: {error}")

    scheduler._process_one_msg = process_wrapper
    scheduler.send_result = send_wrapper
    scheduler._schedule_next_batch = schedule_wrapper
    scheduler.shutdown = shutdown_wrapper
    return adapter


def run_scheduler(args: Any, ack_queue: Any) -> None:
    """Drop-in replacement for ``freetoken.server.launch._run_scheduler`` for this launcher."""
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
            # One detokenizer output stream belongs to rank zero.  Secondary TP ranks keep
            # their unmodified scheduler lifecycle and cannot claim output delivery.
            if args.tp_info.is_primary():
                base = os.environ.get("FT_D16_EXECUTION_ID")
                if os.environ.get("FT_D16_SERVICE_CAPTURE_DIR") and not base:
                    raise ServiceCaptureError("FT_D16_EXECUTION_ID is required for enabled capture")
                if base:
                    os.environ["FT_D16_EXECUTION_ID"] = f"{base}:tp{args.tp_info.rank}"
                install_scheduler_capture(scheduler)
            scheduler.sync_all_ranks()
    except Exception as error:  # preserve the upstream startup error reporting contract
        _report_startup_error(ack_queue, error)
        raise

    if args.tp_info.is_primary():
        # Keep the upstream readiness/meta contract intact; the only difference is the
        # already-installed instance-local capture wrapper above.
        try:
            from freetoken.kvcache.cache_status import compute_cache_status_meta

            meta = compute_cache_status_meta(scheduler.engine)
            meta["gpus"] = scheduler.gpus
            ack_queue.put(("meta", meta))
        except Exception:
            pass
        ack_queue.put("Scheduler is ready")
        set_progress_sink(None)
    if args.silent_output:
        logging.disable(logging.INFO)
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        from freetoken.utils import init_logger

        logger = init_logger(__name__)
        scheduler.shutdown()
        if args.tp_info.is_primary():
            print()
            logger.info("Scheduler exiting gracefully...")


def main(argv: list[str] | None = None) -> None:
    """Launch the normal server, with this worker replacement only when explicitly enabled."""
    from freetoken.server import launch as launch_module

    if os.environ.get("FT_D16_SERVICE_CAPTURE_DIR"):
        launch_module._run_scheduler = run_scheduler
    launch_module.launch_server(argv=argv)


if __name__ == "__main__":
    main()
