"""Scheduler-owned D15 cache adaptation boundary.

The boundary is intentionally entered before scheduling a new batch.  It drains
only the preceding forward, rather than waiting for runnable work to disappear,
then proves that every stream which can read or publish the cache is complete.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdaptationBoundaryResult:
    status: str
    drained_last_data: bool = False


class _StreamReceipt:
    """A proof receipt backed by a concrete, already-synchronized stream."""

    def __init__(self, stream):
        self._stream = stream
        self.device = stream.device

    def query(self) -> bool:
        return bool(self._stream.query())


class AdaptationBoundary:
    """Close launch, drain the preceding forward, then transact before relaunch."""

    def __init__(self, scheduler_identity: str):
        self.scheduler_identity = scheduler_identity

    @staticmethod
    def is_pending(cache) -> bool:
        return cache.adaptation_pending()

    def run(self, cache, last_data, drain_last_data, scheduler_stream, engine_stream) -> AdaptationBoundaryResult:
        """Run one opt-in boundary; callers must not launch until this returns.

        ``drain_last_data`` owns the scheduler's request/result accounting and
        physically synchronizes its actual ``copy_done_event``.  The receipt is
        retained below and queried only after every relevant stream is drained.
        """
        coordinator = cache.runtime_adaptation_coordinator(self.scheduler_identity)
        if coordinator is None:
            return AdaptationBoundaryResult("locked" if cache.adaptation_launch_blocked() else "disabled")
        gate = coordinator.close_launch_gate(cache.next_adaptation_launch_generation())
        completed_events = ()
        if last_data is not None:
            drain_last_data(last_data)
            completed_events = (last_data[1].copy_done_event,)

        streams = [engine_stream, scheduler_stream]
        prefill_stream = getattr(cache, "prefill_copy_stream", None)
        if prefill_stream is not None:
            streams.append(prefill_stream)
        unique_streams = []
        seen = set()
        for stream in streams:
            if id(stream) not in seen:
                seen.add(id(stream))
                stream.synchronize()
                unique_streams.append(stream)

        proof = coordinator.issue_proof(
            gate,
            completed_events,
            tuple(_StreamReceipt(stream) for stream in unique_streams),
        )
        if proof is None:
            return AdaptationBoundaryResult("indeterminate", last_data is not None)
        plan = cache.plan_profile_adaptation(proof)
        if plan.status != "verified":
            return AdaptationBoundaryResult(plan.status, last_data is not None)
        result = cache.apply_profile_adaptation(plan, proof)
        return AdaptationBoundaryResult(result.status, last_data is not None)
