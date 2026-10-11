#!/usr/bin/env python3
"""R057 model-worker memory-history observer.

The parent CLI process does not import torch or make the snapshot directory.
``__mp_main__`` runs in every FreeToken child (including tokenizers), so it
only installs hooks.  CUDA history is enabled by the worker which constructs
the real Engine.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time
from pathlib import Path

MAX_HISTORY_ENTRIES = 200_000


def _birth() -> dict:
    fields = (Path("/proc") / str(os.getpid()) / "stat").read_text().rpartition(") ")[2].split()
    ticks = int(fields[19])
    return {"pid": os.getpid(), "start_ticks": ticks, "execution_id": f"{os.getpid()}:{ticks}",
            "pgid": int(fields[2]), "session": int(fields[3])}


def _write(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def _sample(events: Path, event: str, **extra: object) -> None:
    import torch
    worker = _birth()
    service = json.loads(os.environ["R057_SERVICE_BIRTH"])
    row: dict[str, object] = {"schema": "ft_r057_memory_sample/v1", "event": event,
                              "pid": os.getpid(), "time_ns": time.time_ns(), "service_birth": service,
                              "worker_birth": worker, **extra}
    free, total = torch.cuda.mem_get_info(0)
    row.update(free_bytes=int(free), total_bytes=int(total),
               allocated_bytes=int(torch.cuda.memory_allocated(0)),
               reserved_bytes=int(torch.cuda.memory_reserved(0)))
    _write(events, row)


def _snapshot(snapshot_dir: Path, event: str) -> None:
    import torch
    target = snapshot_dir / f"{time.time_ns()}_{event}.pickle"
    torch.cuda.memory._dump_snapshot(str(target))
    _write(snapshot_dir / "snapshots.jsonl", {"schema": "ft_r057_snapshot/v1", "event": event,
                                                "path": str(target), "pid": os.getpid(),
                                                "time_ns": time.time_ns()})


def _safe_snapshot(events: Path, snapshot_dir: Path, event: str) -> None:
    try:
        _snapshot(snapshot_dir, event)
    except BaseException as exc:
        _write(events, {"schema": "ft_r057_memory_sample/v1", "event": "snapshot_error",
                        "pid": os.getpid(), "time_ns": time.time_ns(), "error": repr(exc),
                        "requested_event": event})


def install(snapshot_dir: Path) -> None:
    """Hook all spawn children; activate CUDA only in the Engine owner."""
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.scheduler.scheduler import Scheduler

    engine_init, process_msg, reply = Engine.__init__, Scheduler._process_one_msg, SchedulerIOMixin._reply_tokenizer_rank0
    forward = getattr(Scheduler, "_forward", None)
    enabled = False
    events = snapshot_dir / "memory_samples.jsonl"

    def enable_for_model_worker() -> None:
        nonlocal enabled
        if enabled:
            return
        import torch
        snapshot_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        torch.cuda.memory._record_memory_history(enabled="all", context="all", stacks="all", max_entries=MAX_HISTORY_ENTRIES)
        _write(events, {"schema": "ft_r057_memory_sample/v1", "event": "history_enabled",
                        "pid": os.getpid(), "time_ns": time.time_ns(), "max_entries": MAX_HISTORY_ENTRIES,
                        "context": "all", "stacks": "all", "worker_birth": _birth()})
        enabled = True

        def finalize() -> None:
            try:
                _sample(events, "process_exit")
                _safe_snapshot(events, snapshot_dir, "process_exit")
            except BaseException as exc:
                _write(events, {"schema": "ft_r057_memory_sample/v1", "event": "snapshot_error",
                                "pid": os.getpid(), "time_ns": time.time_ns(), "error": repr(exc)})

        atexit.register(finalize)

    def observed_engine_init(self, *args, **kwargs):
        try:
            enable_for_model_worker()
            result = engine_init(self, *args, **kwargs)
            _sample(events, "model_loaded")
            _safe_snapshot(events, snapshot_dir, "model_loaded")
            return result
        except BaseException as exc:
            _write(events, {"schema": "ft_r057_memory_sample/v1", "event": "model_load_error",
                            "pid": os.getpid(), "time_ns": time.time_ns(), "error": repr(exc)})
            _safe_snapshot(events, snapshot_dir, "model_load_error")
            raise

    def observed_process(self, message, *args, **kwargs):
        if type(message).__name__ == "UserMsg":
            _sample(events, "request_before", uid=str(message.uid), history_start_marker=True)
        return process_msg(self, message, *args, **kwargs)

    def forward_uids(args: tuple, kwargs: dict) -> list[str]:
        forward_input = args[0] if args else kwargs.get("forward_input")
        reqs = getattr(getattr(forward_input, "batch", None), "reqs", ())
        return [str(getattr(request, "uid", request)) for request in reqs]

    def observed_reply(self, messages):
        for message in messages:
            if type(message).__name__ == "DetokenizeMsg" and bool(message.finished):
                _sample(events, "request_after", uid=str(message.uid))
                _safe_snapshot(events, snapshot_dir, "request_after")
        return reply(self, messages)

    Scheduler._process_one_msg = observed_process
    SchedulerIOMixin._reply_tokenizer_rank0 = observed_reply
    Engine.__init__ = observed_engine_init
    if forward is not None:
        def observed_forward(self, *args, **kwargs):
            try:
                return forward(self, *args, **kwargs)
            except BaseException as exc:
                _sample(events, "request_error", uids=forward_uids(args, kwargs), error=repr(exc))
                _safe_snapshot(events, snapshot_dir, "request_error")
                raise
        Scheduler._forward = observed_forward


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("ft_args", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if not options.ft_args or options.ft_args[0] != "--":
        parser.error("pass ft arguments after --")
    # Parent deliberately stays torch-free and only conveys this path through
    # the environment: spawn no longer retains this script's CLI arguments.
    os.environ.setdefault("R057_SERVICE_BIRTH", json.dumps(_birth(), sort_keys=True))
    os.environ["R057_SNAPSHOT_DIR"] = str(options.snapshot_dir)
    from freetoken.cli import main as ft_main
    sys.argv = ["ft", *options.ft_args[1:]]
    ft_main()
    return 0


if __name__ == "__mp_main__":
    snapshot = os.environ.get("R057_SNAPSHOT_DIR")
    if not snapshot:
        raise RuntimeError("R057 worker lacks parent snapshot directory binding")
    install(Path(snapshot))
elif __name__ == "__main__":
    raise SystemExit(main())
