"""R040a D16 service-capture shutdown wrapper.

This is a new startup wrapper for the R040a source package.  It preserves the
existing D16 hooks but translates the owned lifecycle's SIGTERM into the same
controlled scheduler shutdown path used for KeyboardInterrupt, so the capture
adapter can seal ``service_delivery.json`` exactly once.
"""
from __future__ import annotations

import json
import logging
import os
import signal
from typing import Any


class NativeCaptureShutdownError(RuntimeError):
    pass


def read_sealed_service_delivery(arm: str | os.PathLike[str]) -> dict[str, Any]:
    """Read the post-stop capture or identify a harness shutdown failure."""
    path = os.fspath(arm)
    from pathlib import Path
    delivery = Path(path) / "capture" / "service_delivery.json"
    if delivery.is_symlink() or not delivery.is_file():
        raise NativeCaptureShutdownError(f"D16 harness failure arm={path} delivery={delivery}: service_delivery.json was not sealed after owned stop")
    try:
        document = json.loads(delivery.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeCaptureShutdownError(f"D16 harness failure arm={path} delivery={delivery}: invalid sealed service_delivery.json") from exc
    if document.get("terminal") != "complete":
        expected=document.get("expected_deliveries",[]); verified=document.get("deliveries",[])
        delivered={(item.get("uid"),item.get("generation_index")) for item in verified if isinstance(item,dict)}
        missing=next((item for item in expected if isinstance(item,dict) and (item.get("uid"),item.get("generation_index")) not in delivered),None)
        first="none" if missing is None else f"uid={missing.get('uid')},generation={missing.get('generation_index')}"
        raise NativeCaptureShutdownError(f"D16 harness failure arm={path} delivery={delivery}: service delivery did not complete expected={len(expected)} verified={len(verified)} first_missing={first}")
    return document


def run_with_sigterm_shutdown(scheduler: Any) -> bool:
    """Run one scheduler and always use its installed shutdown wrapper once.

    Only the scheduler worker main thread calls this function.  Non-SIGTERM
    errors retain their original exception after the capture-aware shutdown.
    """
    previous = signal.getsignal(signal.SIGTERM)
    shutdown_called = False

    def owned_sigterm(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, owned_sigterm)
    try:
        scheduler.run_forever()
        return False
    except KeyboardInterrupt:
        return True
    finally:
        try:
            if not shutdown_called:
                shutdown_called = True
                scheduler.shutdown()
        finally:
            signal.signal(signal.SIGTERM, previous)


def run_scheduler(args: Any, ack_queue: Any) -> None:
    """Drop-in D16 worker launcher with capture-aware SIGTERM shutdown."""
    from equiv_suite.service_capture import ServiceCaptureError
    from equiv_suite.service_capture_startup import install_scheduler_capture
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
                base = os.environ.get("FT_D16_EXECUTION_ID")
                if os.environ.get("FT_D16_SERVICE_CAPTURE_DIR") and not base:
                    raise ServiceCaptureError("FT_D16_EXECUTION_ID is required for enabled capture")
                if base:
                    os.environ["FT_D16_EXECUTION_ID"] = f"{base}:tp{args.tp_info.rank}"
                install_scheduler_capture(scheduler)
            scheduler.sync_all_ranks()
    except Exception as error:
        _report_startup_error(ack_queue, error)
        raise

    if args.tp_info.is_primary():
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
    graceful = run_with_sigterm_shutdown(scheduler)
    if graceful and args.tp_info.is_primary():
        from freetoken.utils import init_logger
        print()
        init_logger(__name__).info("Scheduler exiting gracefully...")


def install() -> None:
    """Install existing D16 capture hooks, then replace only worker shutdown."""
    import d16_exact_service_startup_v4 as exact
    from freetoken.server import launch
    exact.install()
    launch._run_scheduler = run_scheduler


def main() -> None:
    install()
    from freetoken.cli import main as cli_main
    raise SystemExit(cli_main())


if __name__ == "__mp_main__":
    install()
elif __name__ == "__main__":
    main()
