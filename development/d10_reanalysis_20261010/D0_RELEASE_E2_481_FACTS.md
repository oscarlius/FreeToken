# Release-e2@481 D0 facts and batch163 comparison

Read-only remote verification on 2026-10-10. This supersedes any inference
from the D05 candidate tree for release-e2@481 capability questions.

## Release-e2 source fact

The remote worktree
`/data2/FreeToken/wt/release-e2/python/freetoken/moe/offload_cache.py`
contains `dev_d0_enabled()` and enables it when `FT_DEV_D0` is any value
other than empty/0/false/no/off. `FT_DEV_D0_PATH` selects the output base.
`FT_DEV_D0_TIMELINE=1` enables the optional CUDA-event timeline, bounded by
`FT_DEV_D0_TIMELINE_STEPS` (default 200). At engine construction,
`cache.collect_stats = config.moe_collect_stats or dev_d0_enabled()`.

The same release-e2 source has `decode_miss_stats()` and
`decode_miss_stats_per_layer()`. There was no source occurrence of
`/internal/dev_moe_diag`, `dev_moe_diag`, or a `--moe-collect-stats` CLI flag
in the release-e2 Python tree. Therefore do not plan an HTTP `/debug` or
internal endpoint for this observation without a separate source lookup.

## Actual b163 evidence method

Actual files exist at
`/data2/_shared/runs/ft_rounds/E2-D09-T16-reapply-bd57-20261010/` in
`PARENT_b163`, `NEW_b163`, `CHUNK_PARENT_b163`, and `CHUNK_NEW_b163` as
`d0_decode_steps.jsonl`, `d0_prefill.jsonl`, and `d0_decode.json`.
The actual b163 launch environment set `FT_DEV_D0=1` and
`FT_DEV_D0_PATH=<arm>/d0`; it did not demonstrate an endpoint.

The inspected b163 decode-step records have `bs=1`, `rids=[0]` or `[1]`,
48-element `missing_per_layer`, `missing_total`, and `h2d_bytes`. Thus b163
proves UID-bound *single-request* decode telemetry. It does not prove a
two-lane shared-batch attribution rule.

For a new true `bs=2` row, `missing_total` is the native batch-level count
after cache lookup and cannot be divided by two as an identified lane metric.
`batch_m = missing_total / (2*480)` is only a batch-average normalized by two
possible 480-expert lane activations. Per-lane m needs native lane masks or
per-UID pre-dedup routing/miss accounting; `rids` alone binds participation,
not a split of deduplicated misses.

## Model unit correction

The archived paper formula is
`t_step(B,L) = 13.1 + 0.032*L + 5.3*(B-1) + B*m*1331MB/BW` ms.
`L` is context length in **thousands of tokens**, confirmed by
`PROJECTION_PERF_PLAN_20261003.md` §3.2 and the archived paper §4.3. The
0.032 coefficient is a historical fitted term, not a D0 metric and not a
release-e2 validation result.
