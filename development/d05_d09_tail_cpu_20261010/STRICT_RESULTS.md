# Strict D05/D09 CPU replay results

Created: 2026-10-11 Asia/Shanghai. This is an append-only strict result after the preregistered two-number gate.

## Scope and controls

Both executions used `/data2/FreeToken/venv/bin/python` with `CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`. They import the pinned bd57 worktree at `/data2/FreeToken/wt/d05_hbug_candidate_20261010/python`. Each constructs genuine `Scheduler`, `CacheManager`, `LinearStatePool`, `Req`, and invokes genuine `Scheduler._forward`.

The only temporary resource adapters are `torch.cuda.Stream`, `torch.cuda.set_stream`, and `torch.cuda.stream`; all are restored in `finally`. The CPU model seam calls genuine `Req.complete_one()` once per scheduled request and returns the next-token tensor. It never writes cache lengths, cache results, match results, or predicates.

## Two-number gate

| Case | Script | Fresh CPU result |
|---|---|---|
| D05 | `strict_scheduler_d05_v5.py` | `cached_tokens=13376`, after actual `_forward` gave `forward_cached_len=13554` |
| D09 | `strict_scheduler_d09_v3.py` | sealed UID1 `match_req` gave `target_admission_cached_tokens=20160` |

D09 reads `D09_T17_EXACT_INPUTS.json`, validates donor SHA `24068f95180ac5cca644024d56f749a341df16ceb35574e41c83bb396471142a` and target SHA `22ed510abb88eaaac15e6103fe292ba23d641e18ea01c14fa1f2dce6c4790fbc`, then replays actual UID0 geometry `0→20224→20282→21302` before matching UID1.

## Answers

1. **Q1 — yes, 20282 reaches the hybrid finish path.** UID0's real `_forward` reaches 20282 and Scheduler invokes `snapshot_message_boundary` (`scheduler.py:1189-1193`). The final `cache_req(..., finished=True)` dispatches to `_cache_req_hybrid` (`cache.py:459-463,505`).
2. **Q2 — the exact D09 commit is eligible but returns false at the actual old-handle guard.** At finish its carrier supplies `d09_len=20282` (`cache.py:517-522`). `_commit_d09_exact` observes the preceding native hybrid handle at 20160; `old_handle.cached_len != 0` and it is not `_D09BoundaryHandle`, so it returns false at `cache.py:648-656`. The strict run records no `_d09_entry`; this is the product guard outcome, not a substituted rejection.
3. **Q3 — 20160 is a native mid-chunk track, not 20224 alignment.** The actual producer `attention/linear.py:127-139` calculates `cached_len + ((extend_len-1)//CHUNK_SIZE)*CHUNK_SIZE`. On raw UID0's 0→20224 prefill that is `(20224-1)//64 * 64 = 20160`. The raw state dump independently records UID0 `donate` 20160 and UID1 `resume-device` 20160. 20224 is the later segment endpoint (and is itself 64-aligned), not the donated state boundary.
4. **Q4 — no under the preregistered same-source definition.** Both cases execute identical bd57 bytes in `_cache_req_hybrid`, but their deciding conditions differ: D05 resolves a normal aligned cached prefix at 13376; D09 requires the prior 20160 hybrid handle and hits the exact-commit rejection predicate at line 655. Therefore they are not “same” because the definition requires identical code *and* identical predicate/condition.
5. **Q5 — proposal only, default off; no implementation change.** Add a CPU suite with (a) conventional radix aligned-prefix regression, (b) recurrent hybrid segment geometry plus native `_build_track_metadata` assertion, and (c) PLE state-slot preservation and D09 exact-guard observability. Each test must pin source/input hashes and invoke real `Scheduler._forward` with only resource/model seams. T16 entry requirements: frozen raw inputs and manifest hashes, strict CPU replay passing, explicit predicate outcome, then independent review before any GPU work. Estimate: 1 engineer-day fixtures/pins, 1 engineer-day recurrent+PLE assertions, 0.5 engineer-day independent review and artifact closure.

## Limits

This proves CPU scheduler/cache bookkeeping and the exact observed match boundary. It does not prove GPU kernel numerical equivalence, generation correctness, or a formal T16 acceptance.
