# R045 v11 runtime review — 2026-10-08

Scope: read-only review of `r045_section14_draft_v11/source` and the supplied Linux CPU stage (65 PASS; report SHA `394ebf7714911eb309ae96c0c000aafe04c972430aa77603fba1d28f533287b8`). This is not a FILEdry/startup approval; R040e measured remains a future prerequisite.

## Verified repairs

- `run_stall_ordinary` now has a marker-only `on_first_real` callback. Decode and interference run in separate bounded threads, both are joined, and either error fails the repetition. Decode SSE can continue while the prefill worker waits for the UID-bound physical token, sleeps, and sends prefill.
- `dry_workloads` now probes the real per-repetition input/API/raw-SSE/event-clock/binding writer families for two-decode, pair-short and stall; it also probes observer and SC2/SC3/SC5 outputs.
- Performance explicitly rejects D0, pause and route tracing. H1 is separate, requests three repetitions, then invokes the original D06 `validate_g4` separately for each raw repetition.
- SC2 labels sidecar `time_ns` as its physical clock and SSE `monotonic_ns` as transport-only. It records `clock_domains_must_not_be_subtracted=true`.

## P0 — T05 card e has no per-layer transfer/compute timeline evidence

`sc5_timeline` serializes only `ordinary_observer/inputs.jsonl` and `tokens.jsonl`. These are UserMsg/Detokenize timestamps, not layer-level H2D/copy/compute events. The D06 diagnostic environment enables `FT_DEV_D0_TIMELINE=1` and 20000 steps, and FILEdry names `d0_decode_timeline.jsonl`; however `run_t05_h1_diagnostic` returns D06 validator views and raw H1 output without loading, hashing, or binding `d0_decode_timeline.jsonl` to the three H1 repetitions or proving its two-decode UID coverage.

Minimal repair: preserve the diagnostic `d0_decode_timeline.jsonl` as a SHA-bound artifact, require actual per-layer transfer/compute rows from a genuine two-request, different-content decode scenario, bound to its two UIDs/repetitions; G3 same-prompt remains comparison-only. Keep it diagnostic-only; do not relabel SC5 observer time as layer timing.

## P1 — SC3 缺少可复算的 k/3 合批证据

T05 的 SC3 判据是三次中 `k` 次合为一遍，`k=0` 是有效实测结果；不应强制出现 `#new-seq:2`。v11 的问题在于 `sc3_prefill_evidence` 仅按 `prefill`/`new_seq` 子串过滤日志，既没有按每次 pair 的请求 UID、日志区间或调度事件绑定，也没有输出可复算的三次 `k/3` 分类。因此当前空结果无法区分“已捕获且三次均未合批”与“未捕获对应日志/调度事件”。

最小修复：对每个 repetition 保留请求 UID、相应日志区间及调度事件，输出 `merged`/`not_merged`/`not_captured` 分类和 `k/3`。`not_captured` 必须保留为证据不足，`not_merged` 才可计入 k=0；这不是新增放行门。

## Residual risk

The v11 stall repair and FILEdry expansion are substantive, but neither establishes T05 card e or affirmative SC3 evidence. Do not use its CPU/FILEdry evidence to claim T05 runtime readiness.
