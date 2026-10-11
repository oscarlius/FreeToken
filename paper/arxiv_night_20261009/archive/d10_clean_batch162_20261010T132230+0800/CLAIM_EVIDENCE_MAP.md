# Claim and evidence map

This map is the authoritative scope guard for the English draft. A claim may move to a stronger category only when the listed artifact exists and is independently reviewed.

| Claim | Status in this draft | Local source | Boundary |
| --- | --- | --- | --- |
| Layer-major prefill changes a cold 32K path from eight sweeps to one; TTFT 6.5–6.6 s | Measured / inherited | `paper/FreeToken_MultiGPU_CoExec_v5.2.html`, FTD-20261009-1 | Upstream-kernel benefit is attributed upstream; not a multi-GPU result. |
| Agent turns cluster near one- and two-sweep TTFT tiers of about 2.8 s and 5.6 s | Measured / inherited | v5.2 §4 and FTD-20261009-1 | A descriptive workload observation, not a universal latency distribution. |
| T17 same-structure comparisons pass 28/28 for measured tails 65–8193 | Measured / inherited | v5.2 §7.6; FTD-20261009-1 | Does not cover tails ≤64 or all possible tails ≥65; measured on `a9dca44`, inherited by a stated compatibility bridge only. |
| R045 concurrent decode is 22.030–22.531 tok/s per lane | Measured / new | `development/evening_directive_20261009/INDEPENDENT_PAPER_REVIEW.json`; v5.2 §8 | Four short-prompt requests, two cache states; no proof of overlap, generality, or multi-GPU throughput. |
| Serial model agrees with R045 at roughly 21–23 tok/s | Derived, workload-local | v5.2 §4.4 and §8.1 | Agreement is not validation of every model coefficient or a staggered-overlap gain. |
| D09 reduces selected two-sweep turns to one pass | Proposed prediction; default-off T16 retry1 `kept` | `development/d09_prediction_20261009/CURRENT_PREDICTION.json`, sealed v4 SHA-256 `edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9`; retry1 formal manifest `0bf2dfd9a4b677875f8a9c9a2c876a07fee3c33555f618635d10e9c746b97de0` | The pre-engine digest is not a measurement. The eight-service, 100-call retry1 validates default-off identity only; it does not prove the enabled mechanism. Enabled-path T17, T03b, and T2 remain pending. |
| D10 could yield 33.1–40.0 tok/s per lane; batch155 prototype result | Conditional scenario; measured bounded feasibility `not_met` | Prediction manifest `development/d10_staggered_20261009/prediction_manifest.json`, SHA-256 `3216e1551fba79e09a3cd6b0d24f2ac63e991cdab0bed5ea7c60c7c9179ab7b1`; batch155 terminal and CPU diagnosis | 33.1–40.0 is conditional, not a confidence interval. Candidate `54955f7` entered the eligible branch; profile0 completed two requests (46/58) at 0.8725121807283541/6.967070060487639 tok/s per request, both <=30, and stopped as `not_met`. Profiles1–3 and fixed-256 are unrun; The current candidate's new T16 has not been run. Both prototypes were below the threshold (earlier: 5.855077/1.064367); current measurements cannot distinguish the mechanism from cold-start effects. No causal attribution to a cache-reset implementation defect is supported. |
| E2-R067d records establish D09/T16/T17/D12 acceptance | No | Retry1 formal record; retry2 batch154 sealed result | Retry1 remains limited by mixed geometry. Retry2/batch154 is `FAILED_HARNESS`: one ready service, one private-route HTTP 404, zero valid generations. It supplies no C3 conclusion and leaves D12 unmet. |
| Strata v0.1.41 S1/S2/S3/S4 are same-binary qualifying measurement subsets | Measured subset only | S3 `S3_PARALLEL2_ACTUAL_TERMINAL_INDEPENDENT_REVIEW_V2.json`, SHA-256 `050357…df3bb`; S4 prior raw/rendering review SHA-256 `496253…57992`; S4 current report SHA-256 `0832…884c`, sealed 37-file raw manifest | S1/S2 bind `fb58e0d` and engine `a1f4bc…aa7a0`; S1 is no-MTP/spec2 and S2 adds MTP/spec4/min-p0.5, so this is not MTP-only causal evidence. S3 changes only S2 `parallel=1` to `parallel=2`, but lacks the batch-MTP flag/environment. S4 retains the same binary and `parallel=2`, adds argv/environment opt-in, and loads the draft layer; this still does not prove positive batch-MTP emission or a pure-MTP causal result. The prior S4 review covers sealed raw sources and prior rendering; this native appendix needs fresh root review. S4 actual cold/short prompts are 32,064/2,012, matching S3, with decode 65.29/69.92/71.41/72.34 and 71.08/71.02/73.89 tok/s. Its native `original128` per-user TPS is 21.978336909366092/48.03433456458522 and aggregate 37.86094214010016, not per-lane proof; fixed-256 remains unsupported (45/60; 105/512). Quality 52/60 was not rerun. These qualifying measurements are not product, accepted two-lane, multi-GPU, D09, or D10 acceptance. |
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
