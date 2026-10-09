"""D10 two-lane staggered decode CUDA prototype.

This intentionally is not attached to the serving scheduler yet.  The current
decode path captures one whole ``model.forward`` in a CUDA graph and the
offload cache keeps one mutable LRU plan.  Reusing either of those objects for
two requests would race.  This module is the narrow CUDA primitive needed by a
future scheduler integration: it accepts already-isolated state and cache slot
sets, drives a copy stream and a compute stream with events, and rejects graph
capture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import torch


PreparePhase = Callable[[int], None]
CopyPhase = Callable[[int, tuple[int, ...]], None]
ComputePhase = Callable[[int, tuple[int, ...]], None]


@dataclass(frozen=True)
class StaggeredDecodeLane:
    """Resources owned by one request for the life of one staggered step.

    ``cache_slots`` are staging/cache rows reserved exclusively for this lane;
    ``state_slots`` are request-local KV / recurrent-state rows.  Callers must
    release neither set until :meth:`run_step` returns its completion event.
    """

    name: str
    cache_slots: tuple[int, ...]
    state_slots: tuple[int, ...]
    copy: CopyPhase
    compute: ComputePhase
    prepare: PreparePhase | None = None


class StaggeredDecodePrototype:
    """Schedule copy(A), compute(A)+copy(B), compute(B) for every layer.

    The object is deliberately default-off.  It creates real CUDA streams and
    events only when enabled, and has no synchronize call in its hot path.  The
    final event is the ownership fence that a scheduler must wait on before it
    can recycle either lane's state or cache slots.
    """

    def __init__(self, device: torch.device, *, enabled: bool = False):
        self.device = device
        self.enabled = enabled
        self.copy_stream = None
        self.compute_stream = None

        if enabled:
            if device.type != "cuda":
                raise ValueError("D10 staggered decode requires a CUDA device")
            self.copy_stream = torch.cuda.Stream(device=device)
            self.compute_stream = torch.cuda.Stream(device=device)

    @staticmethod
    def _validate_lanes(lanes: Sequence[StaggeredDecodeLane]) -> None:
        if len(lanes) != 2:
            raise ValueError("D10 staggered decode requires exactly two lanes")
        if lanes[0].name == lanes[1].name:
            raise ValueError("D10 lanes need distinct request identities")
        for lane in lanes:
            if not lane.cache_slots or not lane.state_slots:
                raise ValueError(f"D10 lane {lane.name!r} has no reserved cache/state slots")
            if len(set(lane.cache_slots)) != len(lane.cache_slots):
                raise ValueError(f"D10 lane {lane.name!r} repeats a cache slot")
            if len(set(lane.state_slots)) != len(lane.state_slots):
                raise ValueError(f"D10 lane {lane.name!r} repeats a state slot")
        if set(lanes[0].cache_slots) & set(lanes[1].cache_slots):
            raise ValueError("D10 lanes share expert-cache slots")
        if set(lanes[0].state_slots) & set(lanes[1].state_slots):
            raise ValueError("D10 lanes share decode state slots")

    def run_step(self, layers: int, lanes: Sequence[StaggeredDecodeLane]):
        """Enqueue a two-lane staggered step and return its completion event.

        A lane first computes attention/router state on the compute stream, then
        copies its already-selected expert rows on the copy stream.  The second
        lane's copy is submitted before lane A's routed GEMM, allowing its H2D
        transfer to overlap A's compute.  Each completion waits only for the
        matching lane's ready event.
        """
        if not self.enabled:
            raise RuntimeError("D10 staggered decode is disabled")
        if layers < 1:
            raise ValueError("D10 staggered decode needs at least one layer")
        self._validate_lanes(lanes)
        if torch.cuda.is_current_stream_capturing():
            raise RuntimeError("D10 staggered decode cannot run inside a CUDA graph capture")

        assert self.copy_stream is not None and self.compute_stream is not None
        done = torch.cuda.Event()
        for layer_id in range(layers):
            lane_a, lane_b = lanes
            prepare_a = torch.cuda.Event()
            with torch.cuda.stream(self.compute_stream):
                if lane_a.prepare is not None:
                    lane_a.prepare(layer_id)
                prepare_a.record(self.compute_stream)
            ready_a = torch.cuda.Event()
            with torch.cuda.stream(self.copy_stream):
                self.copy_stream.wait_event(prepare_a)
                lane_a.copy(layer_id, lane_a.cache_slots)
                ready_a.record(self.copy_stream)
            # B's attention/router work makes its copy descriptor available before
            # A's GEMM is launched, but B's transfer itself is submitted after that
            # launch so it can overlap the already-live A kernel.
            prepare_b = torch.cuda.Event()
            with torch.cuda.stream(self.compute_stream):
                if lane_b.prepare is not None:
                    lane_b.prepare(layer_id)
                prepare_b.record(self.compute_stream)
                self.compute_stream.wait_event(ready_a)
                lane_a.compute(layer_id, lane_a.state_slots)
            ready_b = torch.cuda.Event()
            with torch.cuda.stream(self.copy_stream):
                self.copy_stream.wait_event(prepare_b)
                lane_b.copy(layer_id, lane_b.cache_slots)
                ready_b.record(self.copy_stream)
            with torch.cuda.stream(self.compute_stream):
                self.compute_stream.wait_event(ready_b)
                lane_b.compute(layer_id, lane_b.state_slots)
        done.record(self.compute_stream)
        return done



__all__ = ["StaggeredDecodeLane", "StaggeredDecodePrototype"]
