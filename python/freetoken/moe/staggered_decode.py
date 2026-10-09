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

        The compute stream waits only for its own lane's copy-ready event.
        After lane A's compute is enqueued, lane B's copy is enqueued on the
        side stream before lane B waits and computes.  CUDA can therefore
        overlap B's H2D copies with A's kernels.  Whole-forward CUDA graph
        capture is rejected because its addresses and replay semantics are a
        separate execution contract.
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
            for lane in lanes:
                ready = torch.cuda.Event()
                with torch.cuda.stream(self.copy_stream):
                    lane.copy(layer_id, lane.cache_slots)
                    ready.record(self.copy_stream)
                # Deliberately enqueue A's compute before B's copy.  The copy
                # stream is independent, so B's transfer can execute while
                # A's kernel is live; B then waits only for B's ready event.
                with torch.cuda.stream(self.compute_stream):
                    self.compute_stream.wait_event(ready)
                    lane.compute(layer_id, lane.state_slots)

        done.record(self.compute_stream)
        return done


__all__ = ["StaggeredDecodeLane", "StaggeredDecodePrototype"]
