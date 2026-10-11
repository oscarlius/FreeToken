# Closed-loop X/Y runner

Default inert. Run exactly one admitted phase with `--run --phase speed|d0 --admission <sealed-json>`. Each phase performs X/Y only: two AIPerf invocations, each with two requests and concurrency two, or four generation calls. Root may stop/provision between phases. The runner never starts or stops a service.

Raw AIPerf exports are retained. Per-lane decode TPS is defined as `1000 / raw.metrics.inter_token_latency.value` for each request, matching the frozen R045 raw metric. `L_k_tokens` is `usage_prompt_tokens / 1000`.

For D0, the runner records a pre-group row cursor, waits at most one second for the final flush, and admits only new `bs=2` rows. `sum(missing_total)/(steps*2*480)` is named `m_equivalent_shared_batch_per_lane_average`; it is not independent per-UID m. A deduplicated real miss ratio is emitted only if D0 rows expose active counts. The result retains cursor bounds and participating `rids`.
