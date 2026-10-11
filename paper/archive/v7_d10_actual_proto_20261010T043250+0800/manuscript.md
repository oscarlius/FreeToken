# Low-Latency Co-Execution of Host-Memory-Offloaded MoE across GPUs under Shared-Resource Constraints: Expert-Stream Passes and PCIe Time Budgets as Scheduling Cost Units

**Shangfeng Liu**  
Independent researcher  
Draft timestamp: 2026-10-09 22:39:52 +08:00

## Abstract

Host-memory-offloaded mixture-of-experts (MoE) inference keeps routed experts in DRAM and caches only a subset on the GPU. The resulting service time is governed by the number of expert-stream passes and their PCIe time budget, rather than by recomputed token count alone. This paper contributes: (i) a single-GPU evidence record for layer-major prefill, bounded same-structure correctness, capacity, and concurrent decode; (ii) a pass-and-budget cost model; and (iii) a multi-GPU co-execution design expressed as a proposal under shared-host-resource constraints. The measured R045 experiment uses four short-prompt requests in two concurrent pairs on a single RTX 4090. It obtains 22.030–22.531 decode tok/s per lane, below the strict `>30 tok/s` target and consistent only with the workload-local serial-model range of 21–23 tok/s. This is a negative result; it does not demonstrate compute overlap or multi-GPU scaling. Strata v0.1.41 supplies bounded same-binary S1/S2/S3 qualifying measurement subsets, but no accepted two-lane gate, causal MTP-only delta, quality rerun, or fixed-256 acceptance. D09 has a default-off T16 `kept` measurement only; D10 remains a prediction with no prototype result. No KTransformers or llama.cpp baseline is added.

## 1. Introduction

An offloaded MoE runtime faces a different scheduling problem from a fully resident dense model. Routing activates sparse experts, but an expert absent from the GPU cache must be streamed from host memory. A request therefore pays for one or more expert-stream passes. Reducing recomputation can still leave the pass count unchanged, while a boundary that creates one extra pass can dominate the first-token delay of a short continuation.

This paper studies that observation using FreeToken and a host-memory-offloaded Qwen3.8-Flash-Next NVFP4 configuration. Its title retains a multi-GPU scope because a shared-resource design is derived here. The experimental evidence does not yet include a multi-GPU run. Performance assertions about 1×TP4, 2×TP2, and 4×TP1 are thus proposals or derivations, never measurements.

We make three bounded contributions.

1. We consolidate sealed single-GPU evidence: cold layer-major prefill, real Agent traces, extended context capacity, same-structure state comparisons, and the negative R045 concurrent-decode result.
2. We model expert-stream passes and PCIe time budgets as scheduling cost units. The model explains a one-pass tier near 2.8 s and a two-pass tier near 5.6 s in the examined workload.
3. We specify a multi-GPU co-execution design whose admission control is aware of host-memory bandwidth, transferred-pass tokens, rank criticality, and cache ownership.

The paper makes neither a universal correctness claim nor a claim of batch invariance. It also does not convert a command-line option, a CPU preparation artifact, or a capacity-completion observation into a GPU performance result.

## 2. System, terminology, and method

### 2.1 Execution setting

The evaluated single-GPU setting is an RTX 4090 running FreeToken with Qwen3.8-Flash-Next NVFP4 and host-resident expert banks. The v5.2 evidence record binds measurements to sealed rounds, configuration commits, prompts, and artifact manifests. The extended-window observation uses a 98,304-token window and an offload ratio of 0.88. This manuscript reports the source-bound values; it does not claim that they transfer to another GPU, driver, model quantization, or host topology.

### 2.2 Metrics and evidence classes

`TTFT` is first nonempty delta, including reasoning. `TTFO` is first output-content delta. Decode throughput includes reasoning tokens and excludes TTFT. Output length is the actual terminal output length, not the requested maximum.

| Label | Meaning |
| --- | --- |
| Measured | A locally sealed or independently reviewed observation. |
| Derived | A calculation from stated assumptions and recorded values. |
| Proposed | A design, mechanism, or preregistered experiment without GPU acceptance. |
| Pending | A result required to make a stronger claim has not been obtained. |

Cold and warm paths are reported separately. API cache fields can be missing, so native cache accounting is retained where available. Completion without OOM demonstrates capacity for the stated arrival pattern; it does not establish physically simultaneous compute.

### 2.3 Prior systems and comparison boundary

FreeToken is an edge-native MoE serving system that adapts execution to bandwidth conditions [1]. Layered Prefill motivates layer-oriented scheduling [2]. FlexGen, MoE-Lightning, MoE-Infinity, and hybrid CPU–GPU serving work address complementary memory and bandwidth constraints [4–7].

Strata is a local consumer-hardware inference system with compatible APIs [9]. The historical v0.1.39 observation reported 52/60 versus 47/60 task outcomes relative to FreeToken under a shared 60-question protocol, with seven versus eleven truncations. MTP, quantization, and execution path were not isolated. It is retained as provenance only and is not a causal quality or no-MTP result. The qualifying v0.1.41 S1/S2/S3 measurement subsets are described in Section 8; they do not provide an accepted two-lane gate.

## 3. Evidence boundaries for execution paths

Upstream chunked prefill, layer-major prefill, recurrent-state checkpoints, and expert offload address different parts of the execution path. The observed cold 32K layer-major prefill path changes the relevant expert transfer from eight sweeps to one, while upstream prefill-kernel gains remain attributed to upstream. The reported cold TTFT is 6.5–6.6 s under the relevant bound protocol.

Four claims must remain distinct:

* State-copy identity asks whether stored states are exactly copied.
* Same-structure numerical equivalence asks whether a warm path and an independently cold reference with the same request structure agree.
* Final-text equality asks whether decoded text agrees.
* Concurrent isolation asks whether co-running requests remain independent.

After the K1 repair, 28/28 same-structure cold-reference comparisons passed for four state classes, generated tokens, and full text on measured tail lengths 65, 4095, 4096, 4097, 8191, 8192, and 8193. The measurements were made on commit `a9dca44`; the v5.2 record describes a compatibility bridge to `481d3a7`, not a complete rerun on that commit. No conclusion covers tails of 64 or fewer tokens, and the sampled tails do not cover every possible tail above 64.

The current CPU hybrid executor is a negative measured result: its tested variants delivered 1.97, 28.36, 29.21, and 31.94 tok/s, all below a separate offload reference of 36.61 tok/s. It remains disabled by default. This result is not evidence about Strata or a general CPU–GPU-hybrid design.

## 4. Pass-and-budget cost model

### 4.1 Expert-stream passes

Let `p` be the number of expert-stream passes, `V_e` the streamed-expert volume for a pass, `B_pcie` the effective PCIe bandwidth available to this workload, and `T_other` the non-MoE time. A first-order latency model is

`T = p V_e / B_pcie + T_other`.

The equation is a scheduling abstraction. `V_e` can vary with routing and cache state; `B_pcie` is an effective bandwidth affected by host-memory and PCIe contention. The model does not assert constant bandwidth or a layer-resolved transfer trace.

### 4.2 Short-tail tiers

For the sealed Agent workload, the model organizes short tails into an approximately one-pass tier of 2.8 s and a two-pass tier of 5.6 s. The distinction explains why recomputed-token count alone does not account for first-token delay. It also motivates an admission quantity, *pass tokens*: the predicted number of pending expert-stream passes weighted by their transfer time.

The published derivation uses an approximately 233-token transfer equivalence under its stated coefficients. This is not a hardware-independent constant. It is useful only as a recorded conversion factor for the bound system and workload.

### 4.3 Aggregate decode bound

For `n` active lanes, an aggregate decode bound must reserve both per-lane non-MoE work and shared transfer time. Additional lanes can raise utilization only while the shared host-memory and PCIe budget has slack. Once transfer dominates, more cards or replicas can increase contention without reducing a request's transfer critical path.

### 4.4 Serial and ideal staggered scenarios

The existing derivation has a 43.4 ms serial scenario and a 24.0–28.2 ms ideal staggered scenario. The latter corresponds to 35.46–41.67 tok/s per lane. It assumes a realizable phase separation between transfer and compute. It is a derived idealization, not a measured overlap result or confidence interval.

R045 converts its four observed rates to 44.383–45.392 ms per token. Their 0.983–1.992 ms residual relative to the serial coefficient can be conditionally added to the ideal staggered model, yielding 33.1–40.0 tok/s. This is a preregistered conditional scenario for D10; it is not a forecast interval and it must not be reported as achieved throughput.

## 5. Single-GPU scheduling mechanisms

The mechanisms below are deliberately separated from their evidence state.

| Mechanism | Purpose | State | Required evidence before promotion |
| --- | --- | --- | --- |
| M1 / D09 message-boundary checkpoint | Avoid an extra pass for a qualified short continuation | Proposed | Engine binding; T16 default-off identity; T17 new split structures; T03b replay; cold-reverse, hot-ascending, and edit replays. |
| Host-bank reuse | Reuse permitted host-resident expert storage | Measured in bounded prior paths | Must remain configuration- and cache-state-specific. |
| M4/D10 staggered decode | Separate copy and compute phases between two lanes | Proposed | Prototype binding, T16, and per-lane `>30 tok/s` result on both frozen and 256-token workloads. |
| M5 short-tail action | Exploit short segments | Pending | Correctness for tails ≤64 precedes benefit claims. |

### 5.1 D09 preregistration

D09 is the approved second step of M1, default off and isolated from the release path. It may add one checkpoint at the previous message boundary only when prefix length is at least 8192 tokens and the tail is at most 1024 tokens. It reuses the existing host-memory slot; an optional prompt-cache-tail is a second anchor, not arbitrary multi-anchor expansion.

The valid pre-engine seal (prediction payload SHA-256 `edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9`) identifies two eligible historical C_edit shapes. Round 7 has prefix 20,282 tokens, a conservative 1,020-token tail, and baseline TTFT 5.376 s. Round 10 has prefix 22,558 tokens, a 197-token tail, and baseline TTFT 5.324 s. Both have a preregistered prediction of 2.8 s, with scenario range 2.7–2.9 s. These are historical-shape predictions only. The later default-off D09 T16 retry1 is sealed `kept` with eight services and 100 calls (formal manifest SHA-256 `0bf2dfd9a4b677875f8a9c9a2c876a07fee3c33555f618635d10e9c746b97de0`); it establishes only default-off identity. The enabled mechanism, T17, T03b, and T2 remain pending, so this is not D09 mechanism or product acceptance.

### 5.2 D10 preregistration

D10 is a default-off feasibility prototype after D09 GPU acceptance. It reuses R045's two frozen prompts and AIPerf configuration, retains the original `ignore_eos=false` load, and adds an `ignore_eos=true`, 256-token load. Its formal-development gate is both lanes strictly above 30 tok/s and a passing T16 gate. Failure is a result to record, not a condition to hide by changing the protocol.

The prediction was sealed before measurement. The package creates a command plan only: it starts no server, acquires no GPU lock, launches no CUDA, and supplies no overlap measurement. The whole-step graph contract, lane state isolation, cache-slot ownership, transfer-event dependencies, prototype, and GPU acceptance are pending.

### 5.3 R067d terminal record

The historical original `E2-R067d-d20-short-tail-v1` record remains a reclassified `failed_harness` and must not be used as a D09 result. Its original `c17` candidate was CPU-only at that historical point. The separate formal retry1 `E2-R067d-d20-short-tail-retry1` is a sealed `not_met` product round (formal manifest SHA-256 `928bfbbd7fc30f2134c4e5ece5cc5e3d2ac05f2fa6c779a3f604e9090494f12e`; raw manifest SHA-256 `e2e3cf442b0a467a241b10d530920a12cc95893dd371255420f9af7e15bc7fb6`; independent review SHA-256 `12d812dd109023bb3201ec6b0969a81cd3d9802186d8466168f06794ff6b76e9`). It ran four services and eight valid generation calls with the candidate's default `hybrid_radix` cache resolution. The cold 8192+1 A/B cell had `cached_tokens=0` and equal A/B output, but it differed from hot at token 0 (hot 39, cold 248046). That is the configured product stop condition. D12 was not triggered. This retry1 result does not establish D09's enabled mechanism, T16/T17/T03b/T2 acceptance, a throughput result, or D10 completion.

## 6. Multi-GPU co-execution design

### 6.1 Design scope

This section specifies a proposed design, not a benchmark. It compares a single TP4 group, two TP2 groups, and four TP1 groups. Tensor parallelism partitions tensor computation within a group. Pipeline/layer splitting assigns different layers to stages. Replication independently serves requests. They consume host and interconnect resources differently and must not be treated as interchangeable evidence.

### 6.2 Admission and transfer priority

Each request is admitted with an estimate of its remaining pass tokens, cache state, deadline, and rank-critical transfer budget. The executor should prioritize a transfer that gates the rank on the request's critical path, while reserving a bounded budget for other active groups. This prevents an apparently fair byte-level scheduler from repeatedly delaying the transfer that determines first-token completion.

For configuration `g`, let host-read demand be `H_g`, PCIe demand be `P_g`, and per-request transfer lower bound be `L_g`. A necessary feasibility condition is that aggregate demand remains within the host and PCIe budgets. If `sum_g H_g` saturates the relevant host-memory channels, adding GPUs cannot reduce the host-read contribution to `L_g`; it may worsen it. Cache ownership, NUMA placement, and rank placement therefore form part of the scheduler state.

### 6.3 Memory accounting

The design accounts separately for resident weights, GPU expert cache, host expert banks, KV slabs, transfer staging, and framework overhead. It must reserve the shared host-bank footprint before claiming that a group layout fits. The relevant single-GPU capacity observation showed 87K+32K, 32K+32K, and a late 64K arrival during two decodes completing with 377.7 MiB, 1055.7 MiB, and 381.7 MiB minimum free GPU memory respectively. These are capacity observations, not evidence that the requests computed in parallel.

### 6.4 What this design does not establish

No TP2, TP4, multi-GPU, or shared-host-bandwidth measurement has been run for the target configuration. The design does not establish startup compatibility, correct generation, long-context stability, OOM behavior, or throughput. Each requires its own acceptance sequence.

## 7. Single-GPU measurements and correctness

### 7.1 Context-capacity observations

The extended-window experiment is summarized below.

| Workload | Actual prompt | Median TTFO | Median decode | Scope |
| --- | ---: | ---: | ---: | --- |
| 32K | 32,064 | 6.465 s | 34.33 tok/s | Content-only; first cold request reported separately. |
| 64K | 65,424 | 13.13 s | 35.645 tok/s | Content-only. |
| 87K | 87,100 | 18.45 s | 30.3 tok/s | Two fresh services; any-delta; 228 outputs; tool calls. |

Compared with a prior 73,728-token window observation, cold 32K decode changed from 38.3 to 34.33 tok/s (−10.4%) while enabling the 87K case. This is a capacity–speed trade-off across windows, not a same-commit regression.

### 7.2 Correctness boundary

The 28/28 same-structure T17 result covers the listed tails and the four state classes, generated tokens, and full text. A cold request can have different chunk structure, and concurrent output is not guaranteed invariant. The evidence does not license a general claim of deterministic serving.

## 8. R045 feasibility result and bounded Strata comparison

### 8.1 Measured R045 concurrent decode

R045 uses candidate `481d3a7`, AIPerf 0.11.0, two frozen short prompts, and two concurrent pairs. All four results are below the strict `>30 tok/s` per-lane target.

| Group / request | Decode tok/s | TTFT (s) | TTFO (s) | Actual output | Cache state |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 / b6eed489 | 22.425 | 6.181 | 7.979 | 46 | API missing; native 0 |
| 1 / bdfa2cae | 22.531 | 6.130 | 8.411 | 58 | API missing; native 0 |
| 2 / beffbd9f | 22.030 | 5.612 | 7.444 | 46 | API 64; native 64 |
| 2 / a225d90a | 22.206 | 5.560 | 7.877 | 58 | API 64; native 64 |

The measured range agrees with the serial model's approximately 21–23 tok/s range for this workload. The agreement does not show that lanes overlapped out of phase, identify the physical bottleneck, generalize to the 32K scenario, or validate multi-GPU scaling. Early EOS yields 46 or 58 tokens in the two pairs and is part of the reported workload behavior.

### 8.2 Strata S1/S2/S3: valid measurement subsets only

The S2 retry1 independent terminal review classifies the completed one-service, 11-generation-call run as **VALID_MEASUREMENT_SUBSET_ONLY**. It is not product, quality, fixed-256, or two-lane acceptance. The immutable 40-file raw manifest is SHA-256 `6eb616c55d050651951f154c5c35f277c01e31c756e61c17aa23980b78b50850`; the review is SHA-256 `1f83a1666b988aae710980ddb1325b1a6a01082e127147aee5d536a5ac82b6a8`. The preserved original terminal recorded cleanup false. Exact-owner recovery SHA-256 `27b066e85f8c5177cbe2ebc341c6bbce4e700a8f2b95434583a7d257f4bffd4b` shows no extra service or generation, no GPU compute process, and a released lock. Root sealed closure V2 SHA-256 `21cb4de753e1f20ec13d2085e2d4933ea753b2b08e60c200ecff2fb1315cad41` corrects only a caller file-versus-directory readback mismatch; it preserves raw measurement bytes and the verdict.

S1 and S2 fix v0.1.41 at commit `fb58e0d` and the same build/engine SHA-256 `a1f4bc961395b8d347e3e73d48a35c372000006a42ca9c3ea8abd09fb46aa7a0`. S1 uses `--spec 2` without MTP. S2 adds MTP, `--spec 4`, and `--spec-min-p 0.5`; both use `parallel=1` and `suffix-draft=0`. S1's actual-engine slice SHA-256 `fc9f9cce45c58308d583dfa5d07509b7d5822dbc9795b9e74f6f6a1cfe9e37cf` has no draft layer; S2's SHA-256 `efeaa60a06b7f5608b8959ab2bd6bf626f4f152c234b999cd0f6f6304b6257ec` has one. The arms therefore differ in more than MTP, so they support a same-binary combined-configuration observation, not a causal MTP-only estimate.

| Arm / load | TTFT (s) | Decode tok/s | Boundary |
| --- | --- | --- | --- |
| S1, cold 32,064 prompt / 128 output ×4 | 8.385, 7.997, 8.028, 8.045 | 61.40, 63.05, 63.26, 63.35 | cache 0; length |
| S2, cold 32,064 prompt / 128 output ×4 | 8.633, 8.166, 8.201, 8.180 | 77.28, 79.16, 77.93, 74.31 | cache 0; length |
| S1, short 2,012 prompt / 512 output ×3 | 1.562, 1.562, 1.562 | 66.31, 64.49, 60.44 | cache 0; length |
| S2, short 2,012 prompt / 512 output ×3 | 1.609, 1.624, 1.610 | 78.17, 78.02, 80.99 | cache 0; length |

In the two-request `original128` AIPerf group, S1 produced 46/60 output tokens, TTFT 0.303946/1.276153 s, and per-request decode 65.979488/64.622201 tok/s. S2 produced 45/60 tokens, TTFT 0.352403/1.051616 s, and per-request decode 104.860428/102.945640 tok/s. Aggregate output throughput is 48.418169 tok/s for S1 and 64.618921 tok/s for S2; it is group throughput, not a per-lane decode rate. Client concurrency two queues one GPU engine lane and is neither two active GPU decode lanes nor a direct comparison with FreeToken R045.

Both arms sent `ignore_eos=true, max_tokens=256` on the wire, but v0.1.41 did not handle `ignore_eos`: S1 stopped at 45/60 and S2 at 48/60 output tokens with EOS. Neither arm supports fixed-256 acceptance or a fixed-length-throughput result. The historical IQ3_S-versus-FreeToken-NVFP4 52/60 quality observation was not rerun for v0.1.41/S2. It is not new quality validation and does not identify an effect of quantization, MTP, or the local hybrid executor.

S3 changes only `parallel=1` to `parallel=2` from S2 on the same v0.1.41, `fb58e0d`, and engine binary SHA-256 `a1f4bc961395b8d347e3e73d48a35c372000006a42ca9c3ea8abd09fb46aa7a0`. Its actual engine draft-layer slice is SHA-256 `b3e023b42937c5f8c399e6d86548c6df8d1baaaa97586ffa14f5d91b962ae497`, so a draft layer was loaded. It did not opt into batch-MTP: service argv lacks `--batch-mtp` and `STRATA_BATCH_MTP` is absent. Frozen upstream `fb58e0d` `docs/BATCHING.md` requires that flag or environment variable and limits grouped batch-MTP to one GPU. Loaded weights therefore are not evidence that batch-MTP was in use.

The S3 independent terminal review V2 is SHA-256 `050357014e41bb176f3fcd2b6d85767f4f9340733f8e73165bc361df434df3bb` and classifies the one-service, 11-call run as **VALID_MEASUREMENT_SUBSET_ONLY**. Sealed closure V1 SHA-256 `815798883d179b42f2777dab08ce16d7962a8e41ae5863eebd810096c7556477` binds 42 raw files and manifest SHA-256 `25c25830234a2a7c1a28fc5a4f99deae985c4e4bb27664f601534eac3e9940bd`. The preserved terminal's `cleanup_ok=false` was an immutable S2-module `load_v2` error; exact-owner recovery SHA-256 `83f7cc8de00d285aa7073cd16adcd45ac3be2f9ce1dd5b12b8216022b6cafea0` released the owned resources and is not a product `not_met` result.

| Load | S2, parallel=1 | S3, parallel=2 | Boundary |
| --- | ---: | ---: | --- |
| Cold 32,064 prompt / 128 output ×4, mean decode | 77.17 tok/s | 69.525 tok/s | Throughput fell for these same-build configurations. |
| Short 2,012 prompt / 512 output ×3, mean decode | 79.06 tok/s | 71.80 tok/s | Throughput fell for these same-build configurations. |

For S3 `original128`, actual outputs were 46/60; per-request output throughput was 20.608912/40.556927 tok/s and TTFT was 0.488722/1.532644 s. Aggregate output throughput 35.481136 tok/s and the per-user mean 30.582920 do not show that both lanes exceeded 30 tok/s. Its diagnostic `ignore_eos=true,max_tokens=256` group still stopped at 46/60, with per-request 21.114998/41.678564 tok/s and aggregate 36.291323 tok/s, so it does not support fixed-256. The S2-to-S3 comparison reports lower throughput on these two frozen loads; it is not a general negative conclusion about MTP effectiveness, nor two-lane, multi-GPU, product, quality, D09, or D10 acceptance. The historical 52/60 quality observation remains R001-only and was not rerun.

## 9. Limitations and threats to validity

Host-memory and PCIe contention depend on routing, cache misses, NUMA placement, and competing activity. The pass model abstracts these effects and does not replace a transfer timeline. Context-window values have protocol differences; `any-delta` and content-only metrics are not freely interchangeable. Same-structure correctness is narrower than arbitrary replay correctness, and the unresolved ≤64-tail boundary prevents a broad short-tail claim.

R045 has four requests, two cache states, short prompts, and EOS-limited outputs. It measures a negative gate result but cannot prove or disprove the causal mechanisms behind it. D09 is default-off with its T16 retry1 default-off identity gate `kept`, but that does not prove the enabled mechanism; D10 is in its T16 GPU stage and has no prototype result. Strata has bounded same-binary S1/S2/S3 qualifying measurement subsets but no fixed-256 acceptance, causal MTP-only estimate, quality rerun, or accepted two-lane gate. The multi-GPU section contains no multi-GPU result.

Serving systems can also vary outputs under concurrency and prefix-cache conditions even at temperature zero. vLLM and SGLang document explicit deterministic or batch-invariant modes [10–12]. This paper did not run those modes and does not claim their validation locally.

## 10. Conclusion and reproducibility record

The available evidence supports a narrow conclusion. For the bound host-offloaded single-GPU configuration, expert-stream passes and their PCIe budget explain important first-token tiers, and R045 shows that two concurrent lanes did not meet the strict `>30 tok/s` target: the observed range was 22.030–22.531 tok/s. This negative result agrees with a workload-local serial scenario.

The proposed D09 checkpoint, D10 staggered decode, causal Strata MTP comparison, and multi-GPU layouts should be judged only after their separate sealed GPU acceptance records exist. The accompanying claim/evidence map records each required artifact and prevents a prediction, a bounded one-service subset, or a design from being reported as a broader result.

The historical original R067d remains a reclassified `failed_harness`; the separate retry1 is sealed `not_met` and D12 was not triggered. Neither record promotes D09's enabled mechanism, D10, T16/T17/T03b/T2, D12, or causal Strata MTP comparison to acceptance.

## References

The BibTeX source is in `references.bib`. `CITATION_VERIFICATION.md` records the primary-source URL and access date for every bibliography entry. No DOI is asserted.
