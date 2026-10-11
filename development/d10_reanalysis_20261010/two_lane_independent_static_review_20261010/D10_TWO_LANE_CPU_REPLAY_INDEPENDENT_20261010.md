# D10 two-lane CPU reproduction

**Status: REPRODUCED_KNOWN_DEFECTIVE_BASELINE_NO_STRATEGY_OR_TIMING_CONCLUSION.** Written `2026-10-10T22:49:45.031486+08:00`. This CPU-only replay made no GPU, service, API, or production call.

The original script exactly reproduced its rendered values: G_two batched/stagger/partition **40.52% / 40.39% / 55.01%**; paired seed-real×seed12k **42.95% / 42.91% / 54.52%**. Pins and exact integer counts are in the JSON.

This is a nominal lane-event metric, not UID/distinct-active m. For G_two batched, `29955 / 73920 = 40.52%`, while `29955 / 70334 = 42.59%` using actual distinct active IDs. G_two includes 16 single-lane and 69 two-lane steps, so 154 lane-events—not two equal lanes. Batched misses cannot be attributed to a lane after the combined ensure call.

Stagger confirms its boundary truncation: G_two executes A/B calls `4080/3288` (7368 total) against 7392 represented lane-layer calls; paired traces execute `54000/53976` against 108000. Fixtures also prove load_pair reduces two source prefill histories to `{0}` and a physical clear leaves stale `prev` protection.

The existing values are therefore reproduced, but cannot support a D10 per-lane, strategy, feasibility, or GPU timing conclusion.
