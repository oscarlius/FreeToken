# R048 T09 v7 native trace contract review

Reviewed read-only against `/data2/FreeToken/wt/e2d08` at
`8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`.

`OffloadMoELayer._hybrid_decode` always forms `cpu_ids` and calls
`executor.decode_submit(...)` before the cache copy.  A fully resident route makes
every `cpu_ids` entry `-1`; it does not suppress the submit or trace row.  The C++
executor still submits a `MoeTask`, wakes every worker, and records start/end around
`run_task_body`.  Individual route kernels skip an id below zero, so this is a
valid zero-expert CPU task with nonzero task-completion clocks.

Consequently, the existing candidate has no normal hybrid-decode branch that
emits a trace row with all `cpu_task.start_ns`, `cpu_task.end_ns`, and
`cpu_task.barrier_wait_ns_total` equal to zero.  Such a triple-zero row is not
explained by an all-GPU/hit-only route and must remain fail-closed.

The PCIe trace is different: it brackets `cache.copy_missing()` with CUDA events
on every row.  `event_elapsed_ms == 0` can mean event resolution or no effective
copy work; it does not establish no CPU submission.  The trace has no copy-count
or byte-count field.  Independent D0 records can expose `missing_total`,
`h2d_bytes`, and, in hybrid mode, `cpu_experts`, but those fields are not carried
in the hybrid trace row.

If a future product needs to distinguish a legal no-work submission from a trace
failure, the minimal tooling-only option is to reject triple-zero as today and
cross-bind the already-produced D0 step counters.  The product-contract option is
to add an explicit native task disposition/completion record (for example,
`submitted`, `worker_count`, and `skipped_route_count`) plus a trace copy-count;
then bind acceptance to that new candidate and gate.  Neither option is implemented
by this review.
