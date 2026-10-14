"""Private, opt-in CUDA OOM validation instrumentation. Never ship with the PR."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class FaultPlan:
    def __init__(self) -> None:
        self.steps = 0
        self.injected = False

    def should_inject(self, uids: list[int], epoch: int) -> bool:
        if self.injected or epoch != 0 or 1 not in uids:
            return False
        self.steps += 1
        if self.steps <= 8:
            return False
        self.injected = True
        return True


def injection_enabled(environ: dict[str, str] | None = None) -> bool:
    return (environ or os.environ).get("FT_PR_OOM_INJECT") == "1"


def observer_enabled(environ: dict[str, str] | None = None) -> bool:
    return bool((environ or os.environ).get("FT_PR_OOM_ARTIFACTS"))


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def install_engine_fault(engine_class: type, artifacts: str) -> None:
    """Inject one real CUDA allocation failure only for uid 1 in backend epoch 0."""
    if getattr(engine_class.forward_batch, "_ft_private_oom_probe", False):
        return
    original = engine_class.forward_batch
    plan = FaultPlan()
    destination = Path(artifacts) / "oom_faults.jsonl"

    def forward_batch(self, batch, args):
        uids = [int(req.uid) for req in batch.reqs]
        epoch = int(getattr(getattr(self, "config", None), "backend_epoch", 0))
        if plan.should_inject(uids, epoch):
            import torch

            device_index = torch.cuda.current_device()
            device = f"cuda:{device_index}"
            total = int(torch.cuda.get_device_properties(device_index).total_memory)
            _append(destination, {
                "pid": os.getpid(), "uid": 1, "epoch": epoch, "steps": plan.steps,
                "event": "allocation_attempt", "bytes": total + (1 << 20), "unix_ns": time.time_ns(),
            })
            # This is intentionally a real device allocation beyond total VRAM, not a synthetic error.
            try:
                torch.empty(total + (1 << 20), dtype=torch.uint8, device=device)
            except torch.cuda.OutOfMemoryError as exc:
                _append(destination, {
                    "pid": os.getpid(), "uid": 1, "epoch": epoch, "steps": plan.steps,
                    "event": "actual_exception", "type": type(exc).__name__, "message": str(exc),
                    "unix_ns": time.time_ns(),
                })
                raise
            raise RuntimeError("failed_harness: over-total CUDA allocation unexpectedly succeeded")
        return original(self, batch, args)

    forward_batch._ft_private_oom_probe = True
    engine_class.forward_batch = forward_batch


def _start_ticks(pid: int) -> int | None:
    try:
        # comm is parenthesized and may contain spaces; split only after its closing ')'.
        tail = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(tail[19])
    except (OSError, IndexError, ValueError):
        return None


def install_backend_factory_observer(api_module: Any, artifacts: str) -> None:
    """Record API and every worker generation without changing factory arguments."""
    if getattr(api_module.run_api_server, "_ft_private_factory_probe", False):
        return
    original = api_module.run_api_server
    destination = Path(artifacts) / "backend_handles.jsonl"

    def run_api_server(config, start_backend, run_shell):
        def observed_start(*args, **kwargs):
            handle = start_backend(*args, **kwargs)
            _append(destination, {
                "api_pid": os.getpid(), "api_start_ticks": _start_ticks(os.getpid()),
                "epoch": kwargs.get("backend_epoch", args[0] if args else 0),
                "workers": [{"pid": p.pid, "start_ticks": _start_ticks(p.pid)} for p in handle.processes],
                "unix_ns": time.time_ns(),
            })
            return handle
        return original(config, observed_start, run_shell)

    run_api_server._ft_private_factory_probe = True
    api_module.run_api_server = run_api_server
