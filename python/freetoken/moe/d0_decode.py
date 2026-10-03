"""Optional D0 decode-step telemetry, isolated from the decode hot path."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


_EVENT_NAMES = frozenset(("copy_start", "copy_end", "compute_start", "compute_end"))


def read_sm_clock_mhz(device) -> int | None:
    """Return the selected CUDA device's SM clock, or None when it cannot be read."""
    try:
        if getattr(device, "type", None) == "cpu":
            return None
        visible = [item.strip() for item in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")]
        visible = [item for item in visible if item]
        index = int(getattr(device, "index", 0) or 0)
        target = visible[index] if visible else str(index)
        if getattr(device, "type", None) == "cuda":
            # A CUDA ordinal need not be an nvidia-smi physical ordinal (PCI
            # ordering and CUDA_VISIBLE_DEVICES remapping). Prefer device UUID.
            from freetoken.gpu_select import gpu_identity

            identity = gpu_identity(index)
            if identity["uuid"]:
                target = identity["uuid"]
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,clocks.sm",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, RuntimeError, ImportError):
        return None
    if result.returncode:
        return None
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        gpu_index, gpu_uuid, clock = parts
        if target == gpu_index or gpu_uuid.startswith(target):
            try:
                return int(clock)
            except ValueError:
                return None
    return None


class D0DecodeRecorder:
    """Record cumulative decode counters as per-step deltas when D0 is enabled."""

    timeline = False
    timeline_steps = 200
    compute_scopes = None

    def __init__(
        self,
        base_path: str | os.PathLike[str],
        device,
        timeline: bool = False,
        timeline_steps: int = 200,
        event_factory=None,
    ) -> None:
        if timeline_steps < 0:
            raise ValueError("timeline_steps must be non-negative")
        self.base_path = os.fspath(base_path)
        self.device = device
        self.timeline = timeline
        self.timeline_steps = timeline_steps
        self.event_factory = event_factory
        self.step = 0
        self._active = False
        self._missing: list[int] = []
        self._fetched: list[int] = []
        self._rids: list[int] = []
        self._bs = 0
        self._padded_bs: int | None = None
        self._t = 0.0
        self._origin = None
        self._end = None
        self._events: dict[int, dict[str, object]] = {}

    @property
    def steps_path(self) -> str:
        return self.base_path + "_decode_steps.jsonl"

    @property
    def timeline_path(self) -> str:
        return self.base_path + "_decode_timeline.jsonl"

    def _new_event(self):
        if self.event_factory is not None:
            return self.event_factory()
        import torch

        return torch.cuda.Event(enable_timing=True)

    def _record(self, event) -> None:
        if self.event_factory is not None:
            event.record()
            return
        import torch

        event.record(torch.cuda.current_stream(self.device))

    @staticmethod
    def _counts(name: str, counts) -> list[int]:
        values = list(counts)
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError(f"{name} must contain non-negative integers")
        return values

    def begin(self, batch, missing: list[int], fetched: list[int]) -> None:
        if self._active:
            raise RuntimeError("D0 decode step is already active")
        self._missing = self._counts("missing", missing)
        self._fetched = self._counts("fetched", fetched)
        if len(self._missing) != len(self._fetched):
            raise ValueError("missing and fetched lengths differ")
        self._rids = [req.uid for req in batch.reqs]
        self._bs = batch.size
        if len(self._rids) != self._bs:
            raise ValueError("decode batch rids do not match bs")
        padded_bs = batch.padded_size
        self._padded_bs = padded_bs if padded_bs != self._bs else None
        self._t = time.time()
        self._events = {}
        self._origin = None
        self._end = None
        if self.timeline and self.step < self.timeline_steps:
            self._origin = self._new_event()
            self._record(self._origin)
        self._active = True

    def mark(self, layer: int, name: str) -> None:
        if name not in _EVENT_NAMES:
            raise ValueError(f"unknown D0 timing event {name!r}")
        if not self._active:
            raise RuntimeError("D0 decode step is not active")
        if layer < 0 or layer >= len(self._missing):
            raise ValueError(f"invalid D0 layer {layer}")
        if not self.timeline or self.step >= self.timeline_steps:
            return
        events = self._events.setdefault(layer, {})
        if name in events:
            raise ValueError(f"duplicate D0 timing event for layer {layer}: {name}")
        event = self._new_event()
        self._record(event)
        events[name] = event

    @staticmethod
    def _append(path: str, record: dict) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", buffering=1) as stream:
            json.dump(record, stream, allow_nan=False)
            stream.write("\n")
            stream.flush()

    def seal_timeline(self) -> None:
        """Enqueue the GPU step boundary before counter reads or JSONL writes."""
        if self._active and self.timeline and self.step < self.timeline_steps and self._end is None:
            self._end = self._new_event()
            self._record(self._end)

    def finish(
        self,
        missing: list[int],
        fetched: list[int],
        expert_row_bytes: int,
        hybrid: bool = False,
    ) -> None:
        if not self._active:
            raise RuntimeError("D0 decode step is not active")
        try:
            self.seal_timeline()
            current_missing = self._counts("missing", missing)
            current_fetched = self._counts("fetched", fetched)
            if len(current_missing) != len(self._missing) or len(current_fetched) != len(self._fetched):
                raise ValueError("D0 decode counter lengths changed")
            if expert_row_bytes < 0:
                raise ValueError("expert_row_bytes must be non-negative")
            missing_delta = [now - before for now, before in zip(current_missing, self._missing)]
            fetched_delta = [now - before for now, before in zip(current_fetched, self._fetched)]
            if any(delta < 0 for delta in missing_delta + fetched_delta):
                raise ValueError("D0 decode counters moved backwards")
            if hybrid and any(fetched > missing for missing, fetched in zip(missing_delta, fetched_delta)):
                raise ValueError("hybrid fetched experts exceed missing experts")
            record = {
                "step": self.step,
                "t": self._t,
                "bs": self._bs,
                "rids": self._rids,
                "missing_per_layer": missing_delta,
                "missing_total": sum(missing_delta),
                "h2d_bytes": sum(fetched_delta) * expert_row_bytes,
            }
            if self._padded_bs is not None:
                record["padded_bs"] = self._padded_bs
            if hybrid:
                cpu = [missing - fetched for missing, fetched in zip(missing_delta, fetched_delta)]
                record["cpu_experts_per_layer"] = cpu
                record["cpu_experts"] = sum(cpu)
            self._append(self.steps_path, record)
            if self.timeline and self.step < self.timeline_steps:
                self._finish_timeline()
            self.step += 1
        finally:
            self._active = False

    def _finish_timeline(self) -> None:
        required = set(_EVENT_NAMES)
        if self._origin is None:
            raise RuntimeError("D0 timeline origin is missing")
        if set(self._events) != set(range(len(self._missing))):
            raise ValueError("D0 timeline layers are incomplete")
        for layer, events in self._events.items():
            if set(events) != required:
                raise ValueError(f"D0 timeline events are incomplete for layer {layer}")
        end = self._end
        if end is None:
            raise RuntimeError("D0 timeline end is missing")
        end.synchronize()
        layers = []
        for layer in range(len(self._missing)):
            events = self._events[layer]
            layers.append(
                {name + "_ms": round(self._origin.elapsed_time(events[name]), 3) for name in sorted(events)}
                | {"layer": layer}
                | ({"compute_scope": self.compute_scopes[layer]} if self.compute_scopes is not None else {})
            )
        self._append(
            self.timeline_path,
            {
                "step": self.step,
                "t": self._t,
                "bs": self._bs,
                "rids": self._rids,
                "step_ms": round(self._origin.elapsed_time(end), 3),
                "layers": layers,
            },
        )
