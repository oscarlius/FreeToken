# ARC adaptive-cache CPU supplement

This is exploratory CPU evidence only. It is not the unarchived 20:30 formal full grid, does not set a GPU threshold, and is not a formal pass or acceptance decision.

The replay uses global physical slots, sorted unique routed experts, and physical prefill clearing `[0,1024)`. ARC uses parameter-free T1/T2/B1/B2. Its bounded ghost lists retain identities displaced by that physical clear; the production recipe has no ARC ghost-state contract. Thus the physical clear is exact, while ghost persistence is an explicit implementation limit rather than a runtime-equivalence claim.

The Markov predictor fitted only `G_seed12k`; all other trace values are diagnostic. No heldout data selected ARC settings or supports a throughput claim.

|slots|group|LRU miss rate|LRFU H384|ARC|
|---:|---|---:|---:|---:|
|2700|G_seed12k|37.5287%|35.6772%|37.3619%|
|2700|G_seed_45k|35.5428%|33.9912%|35.3960%|
|2700|G_seed_real|38.5863%|36.8480%|38.9135%|
|2700|G_two|42.5896%|40.7257%|41.0058%|
|2401|G_seed12k|40.4560%|38.5585%|40.4697%|
|2401|G_seed_45k|38.5055%|36.8716%|38.5314%|
|2401|G_seed_real|41.3817%|39.7089%|41.8152%|
|2401|G_two|47.1052%|45.4062%|44.9455%|

LRU exact baseline at 2700: **passed**.
Per-turn missing/active deltas and ARC-minus-LRU regressions are retained in `results.json`.
