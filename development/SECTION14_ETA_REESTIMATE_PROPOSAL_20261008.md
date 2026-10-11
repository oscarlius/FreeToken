# §14 remaining-time re-estimate proposal (2026-10-08 05:53 CST)

This replaces the stale 24–47 GPU-hour estimate with an explicitly conditional schedule. It is a planning estimate, not a delivery date.

| Work item | Current evidence | GPU work remaining | Active-GPU estimate | Wall-clock boundary |
|---|---|---:|---:|---:|
| R040e b104 | 9 of 23 scope reported in progress; 14 remain | 14 cases | unknown: runner timing/reps were not safely available in small metadata | one serialized batch plus closure/review; do not infer from request count |
| R049b v13 | L1 retained by independent 24-request recompute; v13 scope is P1, PA1, L2, P2, PA2, L_D0, P_D0, PA_D0 | 8 services × 24 requests = 192 new requests; no L1 replay | **2.5–6 GPU h** only if ordinary service startup plus generated tokens remain comparable to the prior 9-service plan; 8 fresh service startups dominate | add one serialized slot, D04, independent review, and any early stop on text/not-met |
| R060c gate | new gate, source/runner cardinality not established by this bounded read | unknown | unknown | cannot budget without its arm/request matrix |
| R061b conditional | previous R061a is failed-harness; b is conditional on approval/fix | unknown | unknown | approval plus isolated retry slot |
| T09 v7 / T05 v15 / T11 v5 / T10 v5 / T03b v10 | CPU/readiness status exists, but this pass did not find a common approved GPU queue/cardinality | unknown | unknown | each needs its own formal approval, FILEdry/review and serialized GPU slot |

## Calculation notes

- R049b’s count is derived from the retained-L1 review: 2 cold + 12 seed_45k + 8 seed_real + 2 two-decode = 24 requests per service. The eight remaining services therefore add 192 requests. The retained L1 is a read-only baseline, so it contributes no new GPU work.
- The only defensible R049b duration interval is conditional: the prior 9-service design has workload mix and startup constraints but no completed comparable nine-service timing. Do not convert the 34.33 tok/s sample into a hard runtime lower bound; model load, service readiness, pauses/idle, D04 sealing and independent review are separate wall-clock components.
- CPU preparation currently has no known mandatory development work for signed R049b v13. R040e/R060c/R061b and the five T-cards may need CPU repair after their next evidence; budget 0.5–2 CPU h per newly discovered harness issue, not as committed work.

## Recommended §14 update

Publish `R049b: 2.5–6 active GPU h conditional + closure/review wall-clock` and `R040e/R060c/R061b/T09/T05/T11/T10/T03b: unknown until each runner’s actual arm/request/repetition matrix and authorization are fixed`. The overall remaining duration cannot be responsibly summed today; approval wait, serial GPU ownership, early failure, and unknown-card scopes dominate.

## Supplement: exact request cardinalities recovered from current materials

- **T05 v15**: per service the card specifies two-decode diff `3×2=6`, same `1×2=2`, two stall modes `3×2=6`, pair-short `3×2=6`, and H1 `{1,8,32}×3` with three decodes plus one prefill per rep = `36`; total **56 requests/service**. Service-arm count must be read from v15 runner before a GPU-hour sum; this is a request lower-level estimate only.
- **R049b v13**: **192 newly generated requests** over 8 service starts; retained L1 is 24 existing requests. b102 round timestamps are both `04:50:40`, so they do not provide a service duration. The 2.5–6 h interval is withdrawn pending actual L1 service start/stop metadata; only request cardinality is established.
- **R040e b104**: remaining matrix is 14 scopes: parking 4, cache 4, interleave 6. The observed 9-scope elapsed `47 min` is not extrapolated as a linear fact; a conditional throughput scale would be `14/9×47≈73 min` for comparable scopes, plus model/service startup, D04 and review. Present it as a scenario, not an estimate.
- **R060c**: four gate cases ×128 = **512 target units**; actual request/repetition expansion was not present in the bounded source results, so GPU duration remains unknown.
- **R061b**: conditional on R060c kept; exact fault-injection request scope was not recovered from the bounded metadata, so duration remains unknown.

Therefore user-facing wall clock is bounded chiefly by serialized approvals, cold loads/service starts, D04 and independent review. CPU/FILEdry/R review should be shown separately from active-GPU time.

## b102 L1 wall-clock upper-bound slice

`launch_E2-R049a_batch102.json` has no wall-clock field; its filesystem mtime is `1791404884.7498386`. `E2-R049a/failed_harness.json` likewise has no time field; its mtime is `1791405485.2676256`. Their difference is **600.518 seconds (10.01 minutes)**. Independent review `736e8c...` establishes that b102 completed exactly L1’s 24 requests before this failure. Thus 10.01 minutes is an observed **launch-to-failure upper bound** for one L1, including controller/startup/model-load and the failure path; it is not a performance measurement.

A purely mechanical eight-service scenario is `8 × 10.01 = 80.07 minutes` before D04/independent review and serial scheduling. It must not be used as an actual budget: P/PA and diagnostic configurations were not measured in that timing slice, the failed schema path may have different overhead, and eight separate services may have different cold-load/cache behavior.
