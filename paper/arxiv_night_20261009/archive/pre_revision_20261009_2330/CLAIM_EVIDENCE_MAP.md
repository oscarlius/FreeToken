# Claim and evidence map

This map is the authoritative scope guard for the English draft. A claim may move to a stronger category only when the listed artifact exists and is independently reviewed.

| Claim | Status in this draft | Local source | Boundary |
| --- | --- | --- | --- |
| Layer-major prefill changes a cold 32K path from eight sweeps to one; TTFT 6.5–6.6 s | Measured / inherited | `paper/FreeToken_MultiGPU_CoExec_v5.2.html`, FTD-20261009-1 | Upstream-kernel benefit is attributed upstream; not a multi-GPU result. |
| Agent turns cluster near one- and two-sweep TTFT tiers of about 2.8 s and 5.6 s | Measured / inherited | v5.2 §4 and FTD-20261009-1 | A descriptive workload observation, not a universal latency distribution. |
| T17 same-structure comparisons pass 28/28 for measured tails 65–8193 | Measured / inherited | v5.2 §7.6; FTD-20261009-1 | Does not cover tails ≤64 or all possible tails ≥65; measured on `a9dca44`, inherited by a stated compatibility bridge only. |
| R045 concurrent decode is 22.030–22.531 tok/s per lane | Measured / new | `development/evening_directive_20261009/INDEPENDENT_PAPER_REVIEW.json`; v5.2 §8 | Four short-prompt requests, two cache states; no proof of overlap, generality, or multi-GPU throughput. |
| Serial model agrees with R045 at roughly 21–23 tok/s | Derived, workload-local | v5.2 §4.4 and §8.1 | Agreement is not validation of every model coefficient or a staggered-overlap gain. |
| D09 reduces selected two-sweep turns to one pass | Proposed prediction | `development/d09_prediction_20261009/CURRENT_PREDICTION.json` | Two eligible historical shapes only; engine integration and GPU acceptance are pending. |
| D10 could yield 33.1–40.0 tok/s per lane | Derived conditional scenario | `development/d10_staggered_20261009/PREDICTION_SEAL.json`; plan card | Not a confidence interval or measured performance. Prototype and T16 are pending. |
| Strata v0.1.41 S1 is a no-MTP control; S2 isolates MTP within that build | Proposed experiment | `plan/STRATA_R002_UPGRADE_DIRECTIVE_20261009.md` | S1/S2 have no reported GPU result. v0.1.41 vs v0.1.39 is not a one-variable comparison. |
| Current hybrid executor improves decode | Negative measured result | v5.2 §7.7; FTD-20261009-1 | It did not improve the tested configuration and remains off by default. It does not establish a Strata causal comparison. |
| 1×TP4, 2×TP2, and 4×TP1 improve end-to-end throughput | Proposed design / derivation | v5.2 multi-GPU sections | No multi-GPU performance measurement exists. Tensor parallelism, pipeline splitting, and replicas are separate mechanisms. |

## R045 measured rows

| Group / request | Decode tok/s | TTFT (s) | TTFO (s) | Output tokens | Cache report |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 / b6eed489 | 22.425 | 6.181 | 7.979 | 46 | API missing; native 0 |
| 1 / bdfa2cae | 22.531 | 6.130 | 8.411 | 58 | API missing; native 0 |
| 2 / beffbd9f | 22.030 | 5.612 | 7.444 | 46 | API 64; native 64 |
| 2 / a225d90a | 22.206 | 5.560 | 7.877 | 58 | API 64; native 64 |

`TTFT` is the first nonempty delta, including reasoning. `TTFO` is the first output-content delta. Decode throughput includes reasoning and excludes TTFT. All four rows miss the strict per-lane `>30 tok/s` target.

