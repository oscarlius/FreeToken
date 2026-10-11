"""CPU-only decision model for a future request-level CUDA-OOM supervisor.

This is deliberately not imported by FreeToken. It models the fail-closed
boundary: an in-process CUDA OOM is not proof that allocator, graphs, stream
work, KV writes, or GDN state are safe for the next request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OomDisposition(str, Enum):
    REQUEST_ERROR_RESTART_WORKER = "request_error_restart_worker"
    REQUEST_ERROR_SAFE_CONTINUE = "request_error_safe_continue"
    BATCH_ERROR_RESTART_WORKER = "batch_error_restart_worker"


@dataclass(frozen=True)
class IsolationProof:
    """Evidence required before reusing a worker after a failed request."""

    worker_process_isolated: bool
    no_shared_batch_members: bool
    no_submitted_unjoined_cuda_work: bool
    kv_gdn_transaction_rolled_back: bool
    graph_and_allocator_health_verified: bool

    @property
    def allows_same_worker_continue(self) -> bool:
        return (
            self.worker_process_isolated
            and self.no_shared_batch_members
            and self.no_submitted_unjoined_cuda_work
            and self.kv_gdn_transaction_rolled_back
            and self.graph_and_allocator_health_verified
        )


def classify_cuda_oom(*, batch_size: int, proof: IsolationProof | None) -> OomDisposition:
    """Return the only safe next action; never do cleanup or CUDA work.

    Multi-request batches cannot attribute shared-state writes. A missing proof
    is restart-required, intentionally rejecting ``except OOM: continue``.
    """

    if batch_size != 1:
        return OomDisposition.BATCH_ERROR_RESTART_WORKER
    if proof is not None and proof.allows_same_worker_continue:
        return OomDisposition.REQUEST_ERROR_SAFE_CONTINUE
    return OomDisposition.REQUEST_ERROR_RESTART_WORKER
