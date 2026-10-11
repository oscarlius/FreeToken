# Read-only reuse lookup: R045 two-lane and D0 telemetry

This note is a source lookup only. It authorizes neither a service nor a
measurement and makes no claim about shared-cache throughput.

## Frozen R045 two-request workload

The retained two prompts are in
`development/d10_gpu_night_v1/inputs_r045_v7.jsonl` (also copied by the
R045 packet). They are the fixed A/B/C/D and 1/2/3/4 ordering prompts, each
with `output_length=128`, `temperature=0`, `top_p=1`, and `ignore_eos=false`.
The frozen AIPerf command is `r045_wave1_command.json`: chat streaming,
`--request-count 2 --concurrency 2 --dataset-sampling-strategy sequential`,
`--request-timeout-seconds 300`, builtin tokenizer, server token counting,
legacy max-tokens, and raw export. Its old endpoint and output directory are
historical values and must be replaced only by a newly admitted private
one-service endpoint/output root.

For a future optional D0 observation, retain the two frozen inputs and the
two concurrent requests, bind a fresh private endpoint, use one service, and
bound the whole observation (startup, two requests, D0 collection, shutdown)
to eight minutes. Do not reuse the old R045 production endpoint or artifact
directory.

## Existing shared-cache simulator: what it says and does not say

`two_lane_share_sim.py` uses 48 layers and 512 experts. It deduplicates ids,
refreshes hits before insertion, picks LRU by `(use, slot)`, and clears slots
`[0,1024)` at each listed prefill boundary. For two lanes it reports
`m = misses / (lane_tokens * 480)`; `lane_tokens` is the number of lanes
observed over steps, hence m is a per-lane equivalent miss fraction. Its
`R = 1000 / (2*m*480*(54.77/480))` is an assumed miss-cost upper bound, not a
runtime metric. `batched` is the combined same-layer request set; `stagger`
protects slots used by the immediately previous call; `partition` halves the
cache. This is an open-loop trace replay, not a closed-loop X/Y cache model.

## Reusable D0 per-request decode evidence

Source: `d05_hbug_candidate_20261010/python/freetoken/moe/offload_cache.py`
and `.../moe/d0_decode.py`.

Set `FT_DEV_D0=1` to enable instrumentation and set
`FT_DEV_D0_PATH=<private output base>`. Optional GPU event timelines require
`FT_DEV_D0_TIMELINE=1`; cap with `FT_DEV_D0_TIMELINE_STEPS` (default 200).
The recorder writes:

- `<base>_decode_steps.jsonl`: one record per decode batch with `step`, wall
  timestamp `t`, `bs`, request `rids`, `missing_per_layer`, `missing_total`,
  and `h2d_bytes`; hybrid additionally emits `cpu_experts_per_layer` and
  `cpu_experts`.
- `<base>_decode_timeline.jsonl` only when timeline is enabled: `step`, `t`,
  `bs`, `rids`, `step_ms`, and per-layer CUDA event intervals. This path calls
  `end.synchronize()` only while collecting the bounded timeline.
- `<base>_decode.json`: a cumulative snapshot with `layer_calls`,
  `active_per_layer`, `missing_per_layer`, `miss_rate`,
  `fetched_per_layer`, `cpu_per_layer`, `fetch_rate`, `prefill_hit_rows`, and
  `prefill_rows`, plus `per_layer` records (`steps`, `active_per_step`,
  `missing_per_step`, `miss_rate`, `fetched_per_step`).

Per-request attribution is by the `rids` array in every decode-step record;
it is not an independent per-request cache counter when the two requests
share a decode batch. Compute a lane m only by selecting rows containing the
UID and state the attribution rule; shared-batch `missing_total` must not be
silently counted once per UID. The cumulative `decode.json` is cache-wide,
not request-specific.

`FT_DEV_D0=1` only adds counters/timing. It is not a shared-cache feature
flag. The main config enables the same counters with `moe_collect_stats`.
