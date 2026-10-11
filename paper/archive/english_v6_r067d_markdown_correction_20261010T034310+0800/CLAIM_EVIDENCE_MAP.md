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
| D10 could yield 33.1–40.0 tok/s per lane | Derived conditional scenario; prototype pending | `development/d10_staggered_20261009/PREDICTION_SEAL.json`; plan card | Not a confidence interval or measured performance. Only the T16 GPU stage is active; no prototype result is recorded. |
| E2-R067d original and retry1 establish D09/T16/T17/D12 acceptance | Original reclassified `failed_harness`; retry1 sealed `not_met` | Retry1 formal manifest `928bfbbd7fc30f2134c4e5ece5cc5e3d2ac05f2fa6c779a3f604e9090494f12e`; raw manifest `e2e3cf442b0a467a241b10d530920a12cc95893dd371255420f9af7e15bc7fb6`; independent review `12d812dd109023bb3201ec6b0969a81cd3d9802186d8466168f06794ff6b76e9` | The original historical R067d remains `failed_harness`; its `c17` candidate was CPU-only at that time. Retry1 is a valid four-service, eight-call 8192+1 cold A/B round: both cold outputs agree at cache zero under `hybrid_radix`, but differ from hot at token 0 (39 versus 248046), meeting the configured `not_met` stop condition. D12 was not triggered. It is not D09 enabled-mechanism, T16/T17/T03b/T2, D12, throughput, or D10 acceptance. |
| Strata v0.1.41 S1/S2/S3 are same-binary qualifying measurement subsets | Measured subset only | S3 `S3_PARALLEL2_ACTUAL_TERMINAL_INDEPENDENT_REVIEW_V2.json`, SHA-256 `050357…df3bb`; sealed closure V1 SHA-256 `815798…56477` | S1/S2 bind `fb58e0d` and engine `a1f4bc…aa7a0`; S1 is no-MTP/spec2 and S2 adds MTP/spec4/min-p0.5, so this is not MTP-only causal evidence. S3 changes only S2 `parallel=1` to `parallel=2`, with draft-layer slice `b3e023…ae497`; argv has no `--batch-mtp` and `STRATA_BATCH_MTP` is absent, so loaded draft weights do not establish batch-MTP use. S3 closure binds 42 raw files, manifest `25c258…940bd`, and 11 calls. The same-build cold/short means fell from 77.17/79.06 to 69.525/71.80 tok/s. `original128` per-request output was 20.608912/40.556927 tok/s; aggregate 35.481136 and per-user mean 30.582920 are not per-lane proof. Fixed-256 remains unsupported (46/60); quality 52/60 was not rerun. These qualifying measurements are not product, accepted two-lane, multi-GPU, D09, or D10 acceptance. |
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
