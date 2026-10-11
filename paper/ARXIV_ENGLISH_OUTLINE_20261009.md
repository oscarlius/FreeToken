# English arXiv manuscript outline

**Title (unchanged):** Low-Latency Co-Execution of Host-Memory-Offloaded MoE across GPUs under Shared-Resource Constraints: Expert-Stream Passes and PCIe Time Budgets as Scheduling Cost Units

Author: Shangfeng Liu (刘尚锋), independent researcher. Submission target: arXiv first. This is an outline, not a submitted manuscript. The multi-GPU scope is retained; multi-GPU claims remain analytical derivations and execution proposals.

## Abstract

Introduce host-memory-offloaded MoE inference, where expert streaming and competing PCIe transfers determine latency. State three contributions: single-GPU measurements on RTX 4090 with Qwen3.8-Flash-Next NVFP4; a cost model expressed in expert-stream passes and PCIe time budgets; and a multi-GPU co-execution design constrained by shared host resources. Separate measured results from analytical projections. Mention the R045 result: four concurrent requests achieve 22.03–22.53 decode tok/s per lane, consistent with the serial model and below the >30 target. Do not advertise D09, D10, or Strata no-MTP outcomes before measurement.

## 1. Introduction

Explain why reducing recomputed tokens need not reduce expert-stream passes. Define latency targets, the resource bottleneck, and the distinction between single-GPU evidence and multi-GPU proposals. Preserve the current C1–C5 contribution mapping. No additional KT or llama.cpp baseline is planned.

## 2. System and measurement method

Document hardware, NUMA placement, model quantization and expert layout, runtime commits, context-window settings, and host-bank configuration. Define TTFT (first nonempty delta including reasoning), TTFO (first output content), decode throughput, and actual output length. Bind results to immutable artifacts and distinguish API missing cache fields from native cache accounting. Report cold and warm conditions separately.

## 3. Existing execution paths and evidence boundaries

Describe upstream chunked prefill, layer-major prefill, recurrent-state checkpoints, and expert offload. Attribute upstream kernel gains to upstream. Explain why state-copy identity, same-structure numerical equivalence, final text equality, and concurrent isolation are separate claims. Historical artifacts retain their original verdicts.

## 4. Cost model

Define pass count, streamed expert volume, effective PCIe bandwidth, and non-MoE work. Derive the short-tail one-pass / two-pass latency tiers (~2.8 / ~5.6 seconds), the approximately 233-token transfer equivalence, and the conditional aggregate decode bound. In §4.4 retain the serial 43.4 ms scenario and ideal staggered 24.0–28.2 ms scenario. Label coefficients, assumptions and extrapolation limits explicitly; these are not measured overlap performance or confidence intervals.

## 5. Single-GPU scheduling mechanisms

Present M1–M5 and implementation status separately. D09 is the approved second step of M1: one checkpoint at the previous message boundary under prefix≥8192 and tail≤1024, host-bank reuse, default off. Its preregistered round-by-round predictions precede implementation. D10 is a default-off feasibility prototype of staggered overlap; retain a negative result if either lane fails >30 or T16 fails. Describe admission, interruption, checkpoint-state and graph-contract constraints without implying these proposals have already passed GPU acceptance.

## 6. Multi-GPU co-execution design

Retain tensor-parallel group choices, host-memory bandwidth constraints, pass-token admission, critical-rank transfer priority, and memory accounting for 1×TP4 / 2×TP2 / 4×TP1. Mark all multi-GPU performance as derivation or proposal. Distinguish tensor parallelism from pipeline splitting and replicas. State the host-memory lower bound and assumptions under which additional cards cease reducing transfer time.

## 7. Measurements and correctness

Preserve all current v5.1 measurements, provenance and scope limits. Present layer-major prefill, real Agent traces, host-bank reuse, and the 28/28 sampled same-structure T17 checks. Tail≤64 correctness remains unresolved until R067d is independently closed; sampled tails≥65 do not prove all tails. D09 acceptance must include its new split structures plus reverse-cold, ascending-hot and edit replay. No planned experiment is described in the past tense.

## 8. Feasibility and comparison

Update with R045's four actual decode rates, EOS-limited 46/58 outputs, cold/native0 versus cached64 repeats, and serial-model agreement. Keep capacity completion distinct from compute overlap. Reserve the Strata comparison for R002-mini on existing v0.1.39 without MTP or other drafts, using the frozen R001 recipe and R045 workload. No no-MTP conclusion before argv/stderr checks and measurement. Reuse the historical 52/60 quality result with explicit provenance; do not describe it as newly measured quality for the no-MTP arm.

## 9. Limitations and related work

Discuss shared-memory and PCIe contention, changing miss distributions, context-window tradeoffs, recurrent-state split sensitivity, early EOS, and the gap between prototype overlap and real service throughput. Preserve the current bibliography and attribution; this outline adds no new baseline claims. Explain how a no-MTP control constrains the hybrid negative-result interpretation without assuming its outcome.

## 10. Conclusion and reproducibility appendix

Restate supported single-GPU findings and conditional multi-GPU implications. Provide artifact manifests, model and runtime versions, frozen prompts, command lines, prediction seals, negative results, and independent review records. Before arXiv submission, verify every claim against its evidence level, complete the English manuscript and rendered PDF, and resolve or explicitly disclose pending experiments. Submission itself has not been performed.

Independent review: requested after this outline and the scoped v5.2 draft are produced; the separate review artifact records the actual verdict and gaps.
