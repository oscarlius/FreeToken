# 96K GDN capacity admission: source findings and deferred decision

Date: 2026-10-07. Scope is a local source-only reading of `development/e2base1`; it does not inspect a GPU, endpoint, or executed round.

## Current admission facts

`python/freetoken/scheduler/prefill.py:87-151` keeps an unscheduled request in `PrefillManager.pending_list` when a capacity currency cannot be acquired:

* `table_manager.available_size` is the live request/table-slot gate (line 88).
* Complete prompt-plus-output KV pages are reserved against `CacheManager.available_size` (lines 95-104), including decode tokens reserved by `DecodeManager.inflight_tokens`.
* Hybrid GDN requires one live state slot plus two ping-pong slots; it evicts eligible tree snapshots first, then refuses admission (lines 107-114).
* SWA has a separate per-chunk/window seat check (lines 118-129).

`PrefillManager.schedule_next_batch` scans `pending_list` in order and stops at the first non-admissible request (`scheduler/prefill.py:382-446`). It is FIFO head-of-line capacity waiting, not an ETA/fairness policy. `DecodeManager` tracks admitted `running_reqs` (`scheduler/decode.py:10-39`), while `_schedule_next_batch` gives prefill priority (`scheduler/scheduler.py:1007-1017`).

GDN state is fixed GPU residency: `kvcache/linear_state_pool.py:36-43` allocates conv/recurrent tensors per slot; its free list shares live, ping-pong and tree-snapshot slots (`lines 71-78,139-158`). `CacheManager.ensure_mamba_slots` evicts eligible tree snapshots (`scheduler/cache.py:147-155`). Finished/aborted requests release resources only after an in-flight forward drains (`scheduler/scheduler.py:401-501,744-764`).

## Missing admission currency

No cited scheduler path estimates activation, GDN projection, FLA, or trace workspace. `token_budget` caps scheduled/chunked work (`scheduler/prefill.py:167,305-324`); it is not a workspace reservation. `Scheduler._forward` invokes the engine after batch preparation (`scheduler/scheduler.py:1109-1117`).

The startup cache geometry uses a persisted pre-model baseline, not live free VRAM (`engine/cache_budget.py:31-38,117-124`; `engine/engine.py:356-381`). Its `(1-memory_ratio)` remainder is graph/activation headroom. A request-time `mem_get_info()` gate would drift with allocator caching and undermine the static KV contract; it must not replace KV/GDN-slot admission.

`engine/engine.py:1044-1066` calls layer-major only when `tracer is None`; tracing instead runs normal eager prefill. A single traced request can therefore exceed temporary workspace after all KV/GDN admission checks pass. Waiting cannot make that request fit.

## Decision and future gate

Do not add a new memory-admission queue now. R058 is the authorized production concurrency experiment; only an R058 concurrency OOM establishes the premise for workspace-aware multi-request admission. A single-request OOM is a D07 trace-path/request-isolation issue.

If R058 establishes that premise, a new design must define calibrated static workspace envelopes per execution mode; separate static KV/GDN and dynamic-workspace ledgers; FIFO/aging; bounded queue/cancel timeout; output-budget-inclusive size; end/abort release order; cold-prefix eviction limits; no-progress detection; and an explicitly approximate ETA. A request whose own envelope cannot fit must receive terminal `insufficient_workspace`, never wait indefinitely.

The separate CPU-only containment work is `development/oom_request_isolation_prototype.py` and `development/OOM_REQUEST_ISOLATION_DESIGN_20261007.md`. No product source, PLAN, card, GPU process, or endpoint was changed here.

## R058 completed evidence

R058/batch85 completed all three production scenarios at 0aa23431, 98,304 and .88, with trace/pause/D0 disabled: 87K+32K arrivals, 32K+32K arrivals, and a 64K request submitted during both decodes. Independent raw review and metadata-only D04 closure passed; the round is measured, not kept or release approved. No OOM was observed, so the current user instruction does not call for a new admission queue.

Minimum free-memory samples were 396,034,048 / 1,106,968,576 / 400,228,352 bytes. This is a bounded test result, not a claim that arbitrary loads fit. Arrival-to-first-output wall-clock observations include admission, prefill and return time; they lack direct scheduler-UID binding and do not measure pure queue delay or an ETA. See `plan/01_测试与调研/results/E2-R058_并发显存_20261007.md` for the source and closure hashes and evidence limits.

## 2026-10-07 17:22 已测状态

R058/b85 的87K+32K、32K+32K、双解码中新增64K三场景已measured并D04封存，0 OOM。因此按用户新方向，本轮不新增显存准入队列。结果没有直接测出调度准入时刻或纯队列等待时间，不能将TTFT当成排队时长或承诺ETA；也不证明任意并发安全。D07 layer-major trace修复候选151ee已完成R059四个128臂，纠正复核待用户裁定，尚未放行。
