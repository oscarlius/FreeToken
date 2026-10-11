# D08 T09 completion-observation draft

Scope: this was an isolated patch proposal for an earlier candidate. Its implementation is now
committed as D08 candidate `8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`; this directory remains
review evidence and must not be applied over the candidate.

## Required fields

When `FT_DEV_HYB_TRACE` is absent or not `1`, `trace_enabled` remains false and the native timing branches, CUDA events, stream synchronization, Python trace file, and public timing query are inactive. Existing service behavior is unchanged.

When enabled, each hybrid layer emits:

- `cpu_task.start_ns`, `cpu_task.end_ns`: `steady_clock` timestamps set at pool task execution and final-worker completion.
- `cpu_task.barrier_wait_ns_total`: sum of worker wall time inside phase barriers. It is an aggregate, not a wall-clock latency.
- `pcie_copy.event_elapsed_ms`: CUDA-event elapsed time between events placed immediately before and after `cache.copy_missing()`.
- `pcie_copy.completion_observed_host_ns`: host timestamp after synchronizing the end event. The value proves the event completed, but it is an observation bound, not a device-clock timestamp.

The Python wrapper must call `current_stream().synchronize()` only in the explicit trace branch before reading task timing. That makes CPU completion and copy-event evidence complete; it is diagnostic perturbation and must never be used for performance claims outside T09 trace mode.

## Why an external bootstrap cannot supply this

The current native binding exposes only cumulative worker counts and pin status. The task handle returned by `decode_submit` has no timing accessor; private C++ barriers are invisible. A Python wrapper can time enqueue/sync calls only. A CUDA event after `copy_missing()` needs placement in `_hybrid_routed`; external code cannot reliably insert it around that specific operation or pair it to the layer. Therefore the three candidate files in the diff are necessary.

## Required candidate review

Applying this draft changes the fixed D08 candidate and therefore requires a new candidate commit, CPU/native validation, the D08 T16 gate again, and root/user scheduling review before E2-R048. This draft makes no verdict or measurement claim.

## Flag-coordinator coverage

The default flag-sync coordinator calls `submit(t)` then `sync()` for the registered task before it signals `done_flags`. Both paths wake `worker_loop`, whose first worker sets `trace_start_ns` and whose final worker sets `trace_end_ns`; timing is therefore populated for host-callback and flag-coordinator dispatch. The draft does not treat `flag_served_count` as a timing source.

`MoeTask` keeps these observational atomics `mutable` because `run_task_body(const MoeTask*)` aggregates barrier wait from the existing const worker method. This fixes the const interface without changing task payload semantics.

## Trace-mode interpretation

The proposed `current_stream().synchronize()` is inside the existing explicit trace gate. It ensures completion evidence but perturbs latency and batching; T09 must retain a `trace_mode_perturbs_timing=true` marker and must not use trace-arm tok/s as uninstrumented two-request performance evidence. The D06 two-decode workload remains the end-to-end throughput source; instrumentation supplies causality fields only.

Root CPU syntax check: server g++ -std=c++17 -x c++ -fsyntax-only - accepted the minimal const MoeTask/mutable atomic fetch_add fixture (stdin only, no output binary or candidate changes). This verifies the reported const-atomic issue only; full native extension compilation and GPU measurements remain unverified.
