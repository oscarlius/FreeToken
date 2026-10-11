"""D12-only instrumentation around the existing D16 worker entry and lifecycle.

No request loop, GPU runner, sampler, verdict, or service shutdown is duplicated.
The frozen D16 shutdown module must be on PYTHONPATH for a diagnostic launch.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys

from segment_capture import install_prefill_segment_capture
from transfer_audit import install_transfer_audit
from replay_binding import install_admission_guard, load_from_env


def prepare_environment():
    """Bind the native dump destination before Scheduler imports the state pool."""
    if os.environ.get("FT_D12_DIAGNOSTIC") != "1":
        raise ValueError("D12 worker requires explicit FT_D12_DIAGNOSTIC=1")
    if os.environ.get("FT_DEV_ROUTE_TRACE"):
        raise ValueError("route tracing disables the required layer-major path")
    if os.environ.get("FT_D16_CACHE_INIT") or os.environ.get("FT_D16_PARK_RESTORE") == "1":
        raise ValueError("D12 ordinary-SSE capture does not install R040 cache/parking controls")
    capture = Path(os.environ.get("FT_D16_SERVICE_CAPTURE_DIR", ""))
    if not capture.is_absolute() or "dev_D16" not in capture.parts:
        raise ValueError("D12 requires an explicit existing D16 capture destination")
    dump = capture / "d12_state"
    configured = os.environ.get("FT_DEV_STATE_DUMP")
    if configured is not None and configured != str(dump):
        raise ValueError("FT_DEV_STATE_DUMP conflicts with the D12 capture destination")
    loaded = sys.modules.get("freetoken.kvcache.linear_state_pool")
    if loaded is not None and getattr(loaded, "DUMP_PATH", None) != str(dump):
        raise ValueError("native state pool was imported before D12 dump configuration")
    os.environ["FT_DEV_STATE_DUMP"] = str(dump)
    d0_mode = os.environ.get("FT_D12_D0_COVERAGE", "0")
    if d0_mode not in ("0", "1"):
        raise ValueError("unsupported D12 D0 coverage mode")
    if d0_mode == "1":
        d0_base = str(capture / "d12_d0")
        if os.environ.get("FT_DEV_D0", "1") != "1" or os.environ.get("FT_DEV_D0_PATH", d0_base) != d0_base:
            raise ValueError("native D0 configuration conflicts with D12 capture")
        os.environ["FT_DEV_D0"] = "1"
        os.environ["FT_DEV_D0_PATH"] = d0_base
    tail_mode = os.environ.get("FT_D12_PROMPT_TAIL", "0")
    if tail_mode not in ("0", "1"):
        raise ValueError("unsupported D12 prompt-tail mode")
    if tail_mode == "1":
        from prompt_tail import validate_d03
        validate_d03(os.environ["FT_D12_D03_ROOT"])
        if int(os.environ["FT_D12_TAIL_HIDDEN_BYTES"]) <= 0:
            raise ValueError("D12 retained hidden bound must be positive")
        logits = capture / "d12_prompt_tail"
        if os.environ.get("FT_DEV_LOGITS_DUMP", str(logits)) != str(logits):
            raise ValueError("FT_DEV_LOGITS_DUMP conflicts with D12 prompt-tail destination")
        os.environ["FT_DEV_LOGITS_DUMP"] = str(logits)
    limits = tuple(int(os.environ[key]) for key in ("FT_D12_MAX_EVENTS", "FT_D12_MAX_EVENT_BYTES"))
    if any(value <= 0 for value in limits):
        raise ValueError("D12 event bounds must be positive")
    return capture, dump, limits


def install_worker_capture(scheduler, adapter, capture, dump, limits, replay_binding=None):
    """Attach the two existing observers to one admitted D16 worker instance."""
    if adapter is None or Path(adapter.destination) != capture:
        raise ValueError("D12 requires the existing D16 service adapter")
    engine = scheduler.engine
    if getattr(engine.ctx, "route_tracer", None) is not None:
        raise ValueError("D12 layer-major diagnostic cannot use a route tracer")
    cache = engine.moe_offload_cache
    if cache is None or cache.quant_format != "nvfp4" or cache.prefill_overlap:
        raise ValueError("D12 requires native NVFP4 with prefill overlap disabled")
    if cache.prefill_routed_only_max_tokens not in (0, 256):
        raise ValueError("D12 initial comparison requires threshold 0 or 256")
    uids = tuple(dict.fromkeys(item["uid"] for item in adapter.expected_queries))
    if not uids or any(type(uid) is not int or uid < 0 for uid in uids):
        raise ValueError("D12 expected queries require non-negative integer UIDs")
    if getattr(scheduler.shutdown, "_d12_capture", False):
        raise ValueError("D12 worker capture is already installed")
    capture.mkdir(parents=True, exist_ok=True)
    # A single append-only diagnostic stream remains inside the existing D16
    # evidence directory. D16 admission and D04 sealing own its identity/lifetime.
    events = (capture / "d12_events.jsonl").open("x", encoding="utf-8", newline="\n")
    count = total_bytes = 0
    prompt_tail = None

    def emit(event):
        nonlocal count, total_bytes
        identity = event.get("context", event.get("outer"))
        if not isinstance(identity, dict) or identity.get("uid") not in uids:
            raise ValueError("D12 event has no expected request identity")
        bound = adapter.registry.get(identity["uid"])
        record = {"d12_event_index": count, "process_identity": adapter.capture.process_identity,
                  "physical_event_identity": bound["event_identity"],
                  "prompt_ids_sha256": bound["prompt_sha256"], "evidence": event}
        if replay_binding is not None:
            source = next(row for row in replay_binding["requests"] if row["uid"] == identity["uid"])
            record["frozen_input"] = {"bundle_sha256": replay_binding["bundle_sha256"],
                                      "payload_sha256": source["payload_sha256"],
                                      "input_ids_json_sha256": source["input_ids_json_sha256"]}
        line = json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
        size = len(line.encode("utf-8"))
        if count >= limits[0] or total_bytes + size > limits[1]:
            raise ValueError("D12 diagnostic event budget exhausted")
        events.write(line)
        events.flush()
        count += 1
        total_bytes += size
        if prompt_tail is not None and event["schema"] == "ft_d12_post_prefill_state/v1":
            prompt_tail.observe_state(event)

    restores = []
    try:
        if replay_binding is not None:
            restores.append(install_admission_guard(adapter, replay_binding))
        d0_path = capture / "d12_d0_prefill.jsonl" if os.environ.get("FT_D12_D0_COVERAGE", "0") == "1" else None
        provider, restore = install_prefill_segment_capture(scheduler, dump, emit, allowed_uids=uids, d0_path=d0_path)
        restores.append(restore)
        if os.environ.get("FT_D12_PROMPT_TAIL", "0") == "1":
            if replay_binding is None:
                raise ValueError("D12 prompt tail requires the frozen ordinary input binding")
            from prompt_tail import PromptTailCapture, load_d03
            prompt_tail = PromptTailCapture(engine, replay_binding, dump, capture / "d12_prompt_tail",
                load_d03(os.environ["FT_D12_D03_ROOT"]), provider, emit,
                max_hidden_bytes=int(os.environ["FT_D12_TAIL_HIDDEN_BYTES"]))
            restores.append(prompt_tail.restore)
        # threshold=0 has no routed-only calls, but retains identical outer-state
        # capture. Installing this observer never enables a model feature.
        restores.append(install_transfer_audit(type(cache), emit, provider))
        captured_forward = engine.forward_batch

        def forward(*args, **kwargs):
            try:
                return captured_forward(*args, **kwargs)
            except Exception as exc:
                adapter.record_observer_error(f"D12 forward failed: {type(exc).__name__}: {exc}")
                raise

        def restore_forward():
            if engine.forward_batch is not forward:
                raise RuntimeError("D12 forward ownership changed before cleanup")
            engine.forward_batch = captured_forward

        engine.forward_batch = forward
        restores.append(restore_forward)
    except BaseException:
        try:
            for restore in reversed(restores):
                restore()
        finally:
            events.close()
        raise
    original_shutdown = scheduler.shutdown
    closed = False

    def close():
        nonlocal closed
        if closed:
            return
        closed = True
        errors = []
        if scheduler.shutdown is shutdown:
            scheduler.shutdown = original_shutdown
        else:
            errors.append(RuntimeError("D12 shutdown ownership changed before cleanup"))
        if prompt_tail is not None:
            try:
                prompt_tail.finish()
            except Exception as exc:
                errors.append(exc)
        for restore in reversed(restores):
            try:
                restore()
            except Exception as exc:
                errors.append(exc)
        events.close()
        for error in errors:
            adapter.record_observer_error(f"D12 cleanup failed: {type(error).__name__}: {error}")
        if errors:
            raise errors[0]

    def shutdown():
        try:
            close()
        except Exception as exc:
            # close already registered an observer error. The existing adapter
            # will seal a failed capture; do not mask a native run_forever error
            # through the reused worker's finally -> shutdown call.
            logging.getLogger(__name__).error("D12 teardown failed before native shutdown: %s", exc)
        return original_shutdown()

    shutdown._d12_capture = True
    scheduler.shutdown = shutdown
    return close


def run_scheduler(args, ack_queue):
    """Reuse native D16 capture/shutdown, without R040 exact-ID or parking hooks."""
    if args.tp_info.size != 1 or not args.tp_info.is_primary():
        raise ValueError("D12 initial diagnostic is TP=1 only")
    capture, dump, limits = prepare_environment()
    replay_binding = load_from_env()
    mode = os.environ.get("FT_D12_CAPTURE_POLICY")
    if mode not in (None, "natural-terminal-v1"):
        raise ValueError("unsupported D12 capture policy")
    if mode is not None and (replay_binding is None or "FT_D16_SERVICE_CAPTURE_EXPECTED_JSON" in os.environ):
        raise ValueError("D12 natural capture requires frozen inputs and no fixed-generation declaration")
    from equiv_suite import service_capture_startup as startup
    from d16_native_capture_shutdown_v3 import run_scheduler as native_worker

    original = startup.install_scheduler_capture
    original_factory = natural_factory = None
    if mode is not None:
        from natural_capture import NaturalServiceCapture

        max_captures = int(os.environ["FT_D16_SERVICE_CAPTURE_MAX_CAPTURES"])
        max_bytes = int(os.environ["FT_D16_SERVICE_CAPTURE_MAX_BYTES"])

        def natural_factory(engine):
            return NaturalServiceCapture(capture, binding=replay_binding, max_captures=max_captures,
                                         max_bytes=max_bytes).attach(engine)

        original_factory = startup.install_from_env
        startup.install_from_env = natural_factory
    cleanups = []

    def install(scheduler):
        adapter = original(scheduler)
        cleanups.append(install_worker_capture(scheduler, adapter, capture, dump, limits, replay_binding))
        return adapter

    startup.install_scheduler_capture = install
    primary_error = None
    try:
        return native_worker(args, ack_queue)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_errors = []
        if startup.install_scheduler_capture is install:
            startup.install_scheduler_capture = original
        else:
            cleanup_errors.append(RuntimeError("D12 startup hook ownership changed"))
        if natural_factory is not None:
            if startup.install_from_env is natural_factory:
                startup.install_from_env = original_factory
            else:
                cleanup_errors.append(RuntimeError("D12 capture factory ownership changed"))
        for close in reversed(cleanups):
            try:
                close()
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            if primary_error is not None:
                for error in cleanup_errors:
                    logging.getLogger(__name__).error("D12 cleanup also failed while preserving %s: %s: %s",
                        type(primary_error).__name__, type(error).__name__, error)
            else:
                raise cleanup_errors[0]


def main():
    prepare_environment()
    load_from_env(required=True)
    if os.environ.get("FT_D12_CAPTURE_POLICY") != "natural-terminal-v1":
        raise ValueError("D12 ordinary launcher requires the explicit natural-terminal-v1 policy")
    from freetoken.server import launch
    launch._run_scheduler = run_scheduler
    from freetoken.cli import main as cli_main
    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
