# Request-level CUDA OOM isolation: CPU prototype design

## Goal and non-goal

The goal is a terminal error for an OOM-causing request without silently corrupting or misattributing other requests. It is not permission to catch an OOM in `Scheduler._forward()` and continue the current worker. This is an unmerged CPU-only design and prototype; no FreeToken product tree changes.

## Source impact analysis

`Scheduler._forward` loads mapped input ids, may snapshot a tool-call anchor, executes `engine.forward_batch`, writes sampled output tokens to the shared `token_pool`, then mutates decode membership (`development/e2base1/python/freetoken/scheduler/scheduler.py:1109-1117`). An OOM can occur inside `engine.forward_batch` after kernels, graph replay, tracer begin, multimodal gather, D0 bookkeeping, or GDN-state writes have begun (`engine/engine.py:1034-1088`). The current exception path aborts the tracer and re-raises; it has no transaction rollback.

The shared lifecycle makes a simple exception handler unsafe:

* page-table/KV allocation happens before forward (`scheduler/cache.py:342-361`);
* hybrid admission allocates one live and two ping-pong GDN slots (`scheduler/prefill.py:107-151`);
* normal result processing commits prefix state, frees terminal requests, and changes `finished_reqs` only after copy completion (`scheduler/scheduler.py:401-501`);
* abort waits for an in-flight forward to drain before free, specifically to avoid double-freeing table indices or GDN slots (`scheduler/scheduler.py:649-689`).

CUDA OOM can leave allocator reservations, failed stream work, graph state, or partially written buffers. `empty_cache`, `mem_get_info`, a Python exception, or a per-request KV free is not proof that the worker can safely execute the next request.

## Strict recovery contract

The CPU prototype `oom_request_isolation_prototype.py` returns one of three decisions:

1. A batch containing more than one request is **batch-error/restart-worker**. Shared forward writes prevent reliable per-request attribution.
2. A single request defaults to **request-error/restart-worker**. The supervisor records the failed request identity and stops new work for that worker.
3. **request-error/safe-continue** requires all five independently verifiable proofs: disposable worker-process isolation; exactly one request; no submitted/unjoined CUDA work; transactional KV/GDN/page-table rollback; verified graph and allocator health. Current source lacks this complete proof, so it must choose restart.

The first production-safe implementation is supervisor based: quarantine the failed worker, return an explicit `insufficient_workspace` or `worker_restarting_after_oom` error, and start a replacement only after old-PID exit and independent readiness. Do not replay queued work from mutable in-process state. A shared-batch failure returns a transient batch error and also restarts the worker.

If graceful in-process recovery is ever wanted, it needs a new pre-forward transaction boundary: request-owned page-table/GDN allocations remain unpublished until forward and copy completion; all streams join; graph replay exposure is recorded; global cache/trace/D0 writes are proven absent or rolled back once; and GPU fault-injection verifies all claims. Until then, `except OOM: continue` is unsafe by design.

## Required evidence before any merge

This changes the production failure boundary. It needs user approval, a new product commit, focused CPU tests, GPU fault injection for single/multi-request batches, no-leak checks for KV/GDN/ping-pong slots, graph/trace coverage, restart/readiness evidence, and a new T16 gate. D07 must first restore trace-compatible layer-major chunking. R058 remains the only authorized test of whether concurrent-capacity admission is needed; no new queue is proposed here.
