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


class AdaptationBoundary:
    """Close launch, drain the preceding forward, then transact before relaunch."""

    def __init__(self, scheduler, *, cpu_test_scope: bool = False):
        self._scheduler = scheduler
        self.scheduler_identity = scheduler if isinstance(scheduler, str) else f"scheduler:{id(scheduler)}"
        self._cpu_test_scope = cpu_test_scope

    @staticmethod
    def is_pending(cache) -> bool:
        return cache.adaptation_pending()

    def run(self, cache, last_data, drain_last_data, scheduler_stream, engine_stream) -> AdaptationBoundaryResult:
        """Run one opt-in boundary; callers must not launch until this returns.

        ``drain_last_data`` owns the scheduler's request/result accounting and
        physically synchronizes its actual ``copy_done_event``.  The receipt is
        retained below and queried only after every relevant stream is drained.
        """
        streams = [engine_stream, scheduler_stream]
        prefill_stream = getattr(cache, "prefill_copy_stream", None)
        if prefill_stream is not None:
            streams.append(prefill_stream)
        adaptation_stream = getattr(cache, "_adaptation_copy_stream", None)
        if adaptation_stream is not None:
            streams.append(adaptation_stream)
        unique_streams = []
        seen = set()
        for stream in streams:
            if id(stream) not in seen:
                seen.add(id(stream))
                unique_streams.append(stream)
        coordinator = cache._register_adaptation_boundary(
            self, self._scheduler, self.scheduler_identity, tuple(unique_streams), cpu_test_scope=self._cpu_test_scope,
        )
        if coordinator is None:
            return AdaptationBoundaryResult("locked" if cache.adaptation_launch_blocked() else "disabled")
        copy_done_event = None
        if last_data is not None:
            copy_done_event = last_data[1].copy_done_event
        gate = coordinator.close_launch_gate(cache.next_adaptation_launch_generation(), copy_done_event)
        if gate is None:
            return AdaptationBoundaryResult("indeterminate", last_data is not None)
        if last_data is not None:
            drain_last_data(last_data)
            if not coordinator.mark_last_data_drained(gate, copy_done_event):
                coordinator.abort_gate(gate)
                return AdaptationBoundaryResult("indeterminate", True)
        for stream in unique_streams:
            stream.synchronize()
        if not coordinator.mark_streams_drained(gate, tuple(unique_streams)):
            coordinator.abort_gate(gate)
            return AdaptationBoundaryResult("indeterminate", last_data is not None)
        proof = coordinator.issue_proof(gate)
        if proof is None:
            coordinator.abort_gate(gate)
            return AdaptationBoundaryResult("indeterminate", last_data is not None)
        # Lag-one copies are staged away from live slots.  A later boundary may
        # publish only after the transaction's own completion event reports done;
        # while it is incomplete we retain the old map and never enqueue another.
        if getattr(cache, "_pending_adaptation", None) is not None:
            result = cache.publish_pending_adaptation(proof)
            return AdaptationBoundaryResult(result.status, last_data is not None)
        plan = cache.plan_profile_adaptation(proof)
        if plan.status != "verified":
            return AdaptationBoundaryResult(plan.status, last_data is not None)
        enqueue = getattr(cache, "enqueue_profile_adaptation", cache.apply_profile_adaptation)
        result = enqueue(plan, proof)
        return AdaptationBoundaryResult(result.status, last_data is not None)
