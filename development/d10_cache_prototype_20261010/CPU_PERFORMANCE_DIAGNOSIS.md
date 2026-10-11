# D10 prototype CPU performance diagnosis

**Written:** 2026-10-10T09:31:26.510856+08:00  
**Scope:** read-only diagnosis of `E2-D10-PROTOTYPE-cache-20261010`. This document does not alter the candidate worktree, runner, sealed raw evidence, thresholds, or review state.

## Result

The prototype is **NOT_MET** for profile 0. The terminal receipt records one service, two actual generation calls, and `ValueError('per-request decode speed must be > 30')`; its verdict is `not_met`. The first failed valid profile stopped profiles 1--3, as required. This is a result for this bounded prototype and recipe, not a proof that an ideal staggered-cache mechanism is impossible. Formal development conditions remain unmet and no gate is passed.

The two request-level `output_token_throughput_per_user` values are **0.8725121807283541** and **6.967070060487639 tokens/s/user**, with completion lengths 46 and 58 and TTFT values **20.316885305 s** and **64.321046495 s**. Both are below the `> 30` criterion. The export's aggregate 1.4344312533583339 tokens/s and arithmetic per-user summary 3.919791120607997 tokens/s/user are summaries, not per-lane measurements, and are not used for the verdict.

## Bound evidence

| Evidence | SHA-256 | Direct fact |
|---|---|---|
| Candidate HEAD | `54955f7343fe11c5c0936d18570cfbd826c0f155` | Actual candidate worktree revision. |
| `python/freetoken/engine/engine.py` | `ec9f548eaa544a9549e79a6e46c934f6251f4432da50ea29d7f6196ea5d3d6e4` | Source used by the admission snapshot. |
| `d10_branch_event.json` | `0ba9ebafeb00ec2ce851fb0a08d03a65b53017ff3c62634dcd52e05ed9507f5b` | `Engine._forward_d10_staggered_decode` entered; `actual_can_use_d10_staggered=true`; engine identity `1615483:168964473`. |
| `profile_export_aiperf.json` | `4357bf11e25d2a46d391d530328bbc0cf29f32b928c3a13babaaa6a1bc990ef1` | The two request-level rates, lengths, TTFT, and AIPerf configuration. |
| `serve.log` | `de9a18fcb12ae6b8b3eff8e6400ea5cff87cf744a145967a2aed66db2316a8e7` | D10 flag enabled; profile had two running requests, but two prefill records each have `#new-seq: 1`. |
| `terminal.json` | `bb6c12b64978219d3cc97a93c4851e5affe8f11f59bc3f54658a01f831bfe5fa` | `not_met`, 1 service, 2 calls, no cleanup error. |
| `budget.jsonl` | `f074d0fa406cb88eb3507db4b61ce856289fc75571d84b6a5d746ba3ea4f3ccb` | Calls stopped at group 0, 2 of 8 allowed calls. |

The sealed command used sequential sampling with request-count/concurrency both 2. The serve log records prefill at 09:23:47 for 71 new tokens and again at 09:24:31 for 75 new tokens, each as one new sequence while two requests were running. It then records one decode batch at 09:24:38 with two running requests and 256 tokens. This directly establishes the observed request/prefill layout; it does not establish a clean cold-versus-hot comparison or a root cause for the slow lanes.

The supplied prediction prior is `3216...ab7`, with predicted interval 33.1--40.0 tokens/s/user. It is retained as a prior only: the profile-0 per-request observations are outside it, but this packet did not independently locate an immutable prediction artifact bearing that abbreviated digest, so no stronger source-binding claim is made here.

## Source facts and limits

Direct source facts from the bound engine:

- `engine.py:1103-1112` permits D10 only with the explicit flag, no tracer, a decode batch of exactly two, CUDA, an initialized offload cache, and `forward_staggered_decode`.
- `engine.py:1114-1120` closes a D10 interval before ordinary forwarding by `moe_offload_cache.reset()` and increments `_d10_ownership_epoch`.
- `engine.py:1133-1148` creates two lane caches once; at interval entry resets both lane caches and the shared cache, and rejects an epoch change while active. Consecutive D10 steps therefore retain their lane mappings until a non-D10 batch closes the interval.
- `engine.py:1150-1177` maps each request to a scalar child while retaining its own table/linear row, and assigns cache rows by lane index and cache half; the state slot is that request's `linear_slot_idx`, falling back to `table_idx`.
- `offload_cache.py:1415-1471` creates distinct mutable LRU tensors and disjoint expert-bank slices per lane. It disables prefill-overlap state on lane views and clears pending source-layer state. `offload_cache.py:1241-1247` defines reset as a cache reset plus `expert_recency` invalidation.

The candidate differs from its recorded parent only in `engine.py` and `tests/engine/test_d10_staggered.py`. The existing test file contains five test functions; the parametrized PLE-owner test gives six CPU cases. They cover eligibility/default-off gating, scalar lane isolation, regular sampling normalization, lane-view removal before cache rebuild, and non-disk PLE-owner preparation. They do **not** model the observed service prefill ordering, measure real GPU copy/compute overlap, establish per-lane cache residency at the two prefill points, or identify a performance cause.

## Interpretation boundary

The low measured rates and terminal receipt directly support only: this two-request profile under this recipe failed its per-request threshold. The following are inferences, not established causes: the two one-sequence prefills may have created unequal cache warmness or state at decode; that layout can confound an intended paired-lane throughput interpretation. Neither the raw logs nor the CPU tests attribute the result to cache reset, ownership epoch, non-D10 insertion, lane mapping, PLE, GDN, or copy/compute overlap. No mechanism-negative conclusion follows.

## Minimal next CPU diagnostic

Add one deterministic unit-level trace test, without launching a service or CUDA work, that drives `forward_batch` through: (1) D10 entry, (2) a second consecutive D10 step, (3) one ordinary/non-D10 batch, and (4) D10 re-entry. Record fake cache reset calls, ownership epoch, each lane's row range, request table/linear state slots, and prefill/decode ordering markers. Assert exactly one shared-cache invalidation at first entry, no reset between consecutive D10 steps, one reset/epoch increment on ordinary insertion, and a fresh reset on re-entry. This would distinguish the source's intended ownership lifecycle from the unmeasured runtime ordering without claiming a performance result.
