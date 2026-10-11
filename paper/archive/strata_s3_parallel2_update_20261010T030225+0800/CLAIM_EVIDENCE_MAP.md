# Claim and evidence map

This map is the authoritative scope guard for the English draft. A claim may move to a stronger category only when the listed artifact exists and is independently reviewed.

| Claim | Status in this draft | Local source | Boundary |
| --- | --- | --- | --- |
| Layer-major prefill changes a cold 32K path from eight sweeps to one; TTFT 6.5–6.6 s | Measured / inherited | `paper/FreeToken_MultiGPU_CoExec_v5.2.html`, FTD-20261009-1 | Upstream-kernel benefit is attributed upstream; not a multi-GPU result. |
| Agent turns cluster near one- and two-sweep TTFT tiers of about 2.8 s and 5.6 s | Measured / inherited | v5.2 §4 and FTD-20261009-1 | A descriptive workload observation, not a universal latency distribution. |
| T17 same-structure comparisons pass 28/28 for measured tails 65–8193 | Measured / inherited | v5.2 §7.6; FTD-20261009-1 | Does not cover tails ≤64 or all possible tails ≥65; measured on `a9dca44`, inherited by a stated compatibility bridge only. |
| R045 concurrent decode is 22.030–22.531 tok/s per lane | Measured / new | `development/evening_directive_20261009/INDEPENDENT_PAPER_REVIEW.json`; v5.2 §8 | Four short-prompt requests, two cache states; no proof of overlap, generality, or multi-GPU throughput. |
| Serial model agrees with R045 at roughly 21–23 tok/s | Derived, workload-local | v5.2 §4.4 and §8.1 | Agreement is not validation of every model coefficient or a staggered-overlap gain. |
| D09 reduces selected two-sweep turns to one pass | Proposed prediction | `development/d09_prediction_20261009/CURRENT_PREDICTION.json`, sealed v4 SHA-256 `edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9` | The digest binds a pre-engine prediction, not a measurement. Two eligible historical shapes only; engine integration and GPU acceptance are pending. |
| D10 could yield 33.1–40.0 tok/s per lane | Derived conditional scenario | `development/d10_staggered_20261009/PREDICTION_SEAL.json`; plan card | Not a confidence interval or measured performance. Prototype and T16 are pending. |
| E2-R067d-d20-short-tail-v1 establishes D09/T16/T17/D12 acceptance | Reclassified `failed_harness`; original independent `not_met` preserved | Formal terminal record; independently reviewed semantic record | The 00:35 ruling attributes the scheduled cold failure to naive caching without hybrid ping-pong slots. Append-only reclassification evidence SHA-256 `408b9ede54c25c7038e0b48c4b1b4bc557c3aa51b4b00115290e4673ee7116e7` preserves the original independent verdict. Root stopped after `ValueError: scheduled donor did not build exactly one rewind checkpoint` and `SIGTERM`. Three services and seven calls occurred; six hot completions occurred; no cold A/B cell completed. Cleanup completed, but D12 conditions were unmet. It is neither a D09 GPU measurement nor T16/T17/D12 acceptance. The `c17` candidate is CPU-only and provides no GPU evidence. |
| Strata v0.1.41 S1/S2 are same-binary measurement subsets | Measured subset only | Remote `STRATA_S2_RETRY1_ACTUAL_TERMINAL_INDEPENDENT_REVIEW.json`, SHA-256 `1f83a1666b988aae710980ddb1325b1a6a01082e127147aee5d536a5ac82b6a8`; sealed closure V2 SHA-256 `21cb4de753e1f20ec13d2085e2d4933ea753b2b08e60c200ecff2fb1315cad41` | S1/S2 bind `fb58e0d` and engine `a1f4bc…aa7a0`; S1 is no-MTP/spec2 and S2 adds MTP/spec4/min-p0.5, so the comparison is not MTP-only causal evidence. Both run `parallel=1`; client concurrency 2 queues one engine lane. S2's 40-file raw manifest is `6eb616…50850`, it made 11 calls, and its actual MTP slice is `efeaa…257ec`. Fixed-256 remains unsupported: S1 stops at 45/60 and S2 at 48/60 despite `ignore_eos=true` on the wire. It is not product, quality, two-lane, or multi-GPU acceptance. The historical 52/60 quality observation was not rerun. |
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
