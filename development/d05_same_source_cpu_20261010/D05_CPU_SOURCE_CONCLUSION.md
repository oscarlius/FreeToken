# D05 CPU source conclusion — R052a UID7/UID8 versus bd57 D09

**Verdict: DIFFERENT_SOURCE.** This is a CPU-only, source-bound conclusion. It does not
change the sealed R052a `not_met` record or authorize a service/GPU run.

## Bound inputs

- Sealed R052a raw directory: `/data2/_shared/runs/ft_rounds/E2-R052a-night-20261009-v2`.
  `round.json` SHA256 `a6afa48714be5357c1dc9af157c944541f24768414c94653e1928a8a54d14b8a`,
  `result.json` `14df3c9a04451015bc057a9cc4dad8824678beb9b8665ca88837ecb06982b3cd`,
  `serve.log` `85dea3c2650a3893c781cbe283cfe090bbbf323ebdd77a300a480c4c3b8ab38d`,
  `independent_review.json` `ebac49934dc765d0f91ddfb311c6f806b99ddc50ed3cf490d1747119743dff6d`.
- Candidate source: detached local/remote D05 worktrees at bd57
  `bd57cfdccc2a935d46cb0a89b8b36be7a18706de`. Candidate
  `scheduler/cache.py` SHA256 `c9464937f444cc0693efc9cdcd782c4854e5794c4ce60f191cc59e2851af679c`;
  `scheduler/scheduler.py` SHA256 `3c5235c21af9b67cc7842912d6ac0d18cdf17449fbae81e16aa509d739ab4180`.

## Executed actual path

Remote FT venv executed `test_actual_bd57_r052_replay.py` with the candidate source on
`PYTHONPATH`: **1 passed** (3.93 s; CPU fallback warning only). The test instantiates the
actual `LinearStatePool`, `CacheManager` and `Scheduler._forward`; only the model
forward’s token side effect is CPU-stubbed. It makes an aligned UID6 generic-hybrid donor
at 13,376, admits UID7 through the real cache, drives the real decode scheduler seam to
13,554, then calls the real finished cache path and admits the follow-up.

The exact resulting values were `uid6_donor_cached_len=13376`,
`uid7_final_cached_len=13554`, `floor_64=13504`, `followup_cached_len=13376`, and
`missing_to_floor=128`. `d09_entry_created=false` and `decode_created_track=false`.

D09's bd57 page-conservation branch needs an explicit `message_boundary_carrier` and
`message_boundary_ckpt`; UID7's historical generic decode has neither. The current
`build_fla_metadata` returns its decode metadata before `_build_track_metadata`, while
`CacheManager._cache_req_hybrid` refuses a live finish donation whenever
`align_down(13554,64) != 13554`. Thus the 128-token shortfall is a decode-track/unaligned
finish-donation mechanism, not D09's explicit boundary snapshot/page-transfer mechanism.

## Bounded H-bug repair and diagnostic

The new candidate worktree is `development/d05_hbug_candidate_20261010` locally and
`/data2/FreeToken/wt/d05_hbug_candidate_20261010` remotely. It is detached at bd57 and
unmodified. A 1–2 person-day repair should add an opt-in, page-boundary decode checkpoint
at the target's 13,504 boundary, copying the whole live logical state into the existing
ping-pong slot and making the finished generic-hybrid commit donate that exact state.
It must preserve default-off behavior and add CPU tests for conv, recurrent and PLE state,
then a cold donor-at-P hash gate before any output comparison.

The future T11 diagnostic remains `PENDING_INDEPENDENT_REVIEW_AND_GPU_ADMISSION`: at most
two generation calls (UID7 target then UID8 continuation), a fresh RID, fixed retained
trace inputs, donor/cold full-state hash equality before output, and `failed_harness` on a
mismatch. It must use an owned controller/child, pinned source/native records, actual
route/Effects, file-dry and owned cleanup. No GPU, HTTP, service, lock, or admission was
performed here.
