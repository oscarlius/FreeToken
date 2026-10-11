# D05 R052a cached-token gap: source and UID-bound log finding

## Bound evidence

The formal artifact actually present on the remote is `/data2/_shared/runs/ft_rounds/E2-R052a-night-20261009-v2` (not a `...20261010` directory). Its immutable `round.json` records terminal `not_met`. Its `independent_review.json` records `NOT_MET` / H-bug because the follow-up cache was 13,376, below the source-defined 13,504 threshold. This diagnostic does not change either record.

`result.json` binds the target to server UID 7: `prompt_tokens=13432`, `completion_tokens=122`, so `target_full_tokens=13554`; its threshold is `floor(13554,64)=13504`. The same result binds the only continuation to `history_uid=8`; the bound R052 runner also rejects any target other than `trace_index=7, history_uid=8` before sending that continuation (`/data2/FreeToken/runs/dev_night_tail_queue_20261009/source/runtime_v2_fix/r052a/r052_t11_followup_prepare.py:41-45`). The follow-up response is server UID 8, with `prompt_tokens=13568` and `cached_tokens=13376`.

The matching `serve.log` trajectory is:

| UID | retained evidence | meaning |
| --- | --- | --- |
| 6 | lines 310-313: `12672+768` prefill then `archived boundary 13376` | the host archive belongs to UID 6, not UID 7. |
| 7 | lines 326-329: resumes slot 22; `56/13376`; `cached_len=13433 L=None` | this is the target prefill fragment only. |
| 8 | lines 336-343: resumes slot 22; `64/13376`, then `128/0`; `cached_len=13569 L=13504` and commits `13504` | this is the follow-up after it already reported the 13,376 cache hit. |

Therefore the prior inference from `UID 7: cached_len=13433 L=None` directly to the target's final 13,554 state was unsupported. That log line establishes only that its 56-token prefill did not cross a tracking boundary. It cannot on its own describe the 122-token decode or the later UID 8 continuation.

## Source-level cause of the 128 gap

The bound source gives a narrow explanation for the missing aligned donation at target completion:

- `attention/linear.py:68-73` returns decode metadata before the ordinary tracking branch; that tracker is only constructed on the prefill path at lines 75-86 and writes `mamba_last_track_seqlen` only when a prefill extend contains a completed 64-token crossing (`linear.py:100-134`). There is a separate, conditional tool-call-anchor copy path (`scheduler/cache.py:229-255`, called by `scheduler/scheduler.py:1109-1116`), but `result.json.d0.anchor_snapshots_taken=0` records that it produced no snapshot in this round. Thus UID 7's subsequent 122 generated decode tokens did not produce a 13,504 tracker entry in the retained execution.
- At request finish, `scheduler/cache.py:446-454` computes `insert_len = align_down(req.cached_len, page_size)` but donates the live state only when `insert_len == req.cached_len`. If the target's source-bound full length 13,554 is its final cached length, `insert_len=13504 != 13554`; the finish donation at 13,504 is skipped. The source comments explicitly describe that non-aligned final cached length is skipped at lines 446-450.
- The first logged `L=13504` appears only during UID 8's own new prefill (`serve.log:338-343`), after its cache admission already resumed UID 8 from 13,376. It cannot retroactively raise the cache hit reported for UID 8.

This is sufficient to identify the source-path cause of the 128-token shortfall: target UID 7 crosses the required alignment during decode, while this revision tracks only prefill crossings and refuses an unaligned finish donation. It does **not** establish a broader cache or scheduler defect beyond this target path.

`d05_r052_gap_replay.py` is a CPU-only parser for this concrete UID trajectory. Its test rejects the old two-line argument because it lacks UID 8's separate 13,504 event. It sends no service, HTTP, GPU, lock, or production request.

## Bounded GPU question

No GPU call is needed to establish this source-and-log diagnosis. A future implementation change would need at most two calls only to validate a changed contract: one target UID 7 completion with a receipt for the final cache/donation state, then its exact UID 8 follow-up with cache admission. Neither call is authorized or performed by this diagnostic.
