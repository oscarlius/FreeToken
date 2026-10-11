# D05/D09 tail CPU replay — UNREPRODUCED

Status: **UNREPRODUCED; stop rule applied.** This is not an attribution, a same-source conclusion, or a proposal to change product code.

## Fixed evidence

`PREREGISTRATION.md` SHA-256 is `ef9f5fe22bc51be91d7833aab3ec57ec1fb4a6e1f7e652de25ad809f3c5c0e79`.

The required existing D05 replay was invoked locally at 2026-10-10T23:58+08:00. Test collection failed before its `replay()` function ran because the local Python 3.14 environment has no `torch` (`ModuleNotFoundError`). Thus no `LinearStatePool`, `CacheManager`, or `Scheduler` product path was instantiated and no 13,376 result was produced.

The specified raw D09 round path is remote-only (`/data2/_shared/runs/ft_rounds/E2-D09-T17-reapply-bd57-20261010`) and was not read. The expected round SHA prefix `a6655b59` is therefore unverified in this run. Remote CPU execution needs root's explicit no-GPU timing confirmation, which was not received.

## Required reproduction gate

Both actual results must be observed through identical bd57 code and predicate: D05 `13,376` and D09 `20,160`. Neither was obtained. The source/predicate relation is consequently not established.

| Question | Result |
|---|---|
| Q1: 20,282 reaches `cache_req_hybrid` | UNREPRODUCED |
| Q2: D09 commit/result/failed condition/lines | UNREPRODUCED |
| Q3: 20,160 versus 20,224 | UNREPRODUCED |
| Q4: same-source | UNREPRODUCED |
| Q5: proposal/tests/person-days | Deferred; it depends on Q1–Q4 |

## Next bounded action

With explicit remote CPU-only authorization, run the existing D05 replay and a new D09 replay that reads and SHA-pins the raw carrier, imports the identical bd57 product path, and replaces only token-model side effects. If either required length is absent, preserve `UNREPRODUCED` and stop again.
## Strict replay attempt update (2026-10-11)

Remote CPU-only authorization was used with `CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`.

- The frozen D09 round SHA was read as `a6655b5920069ada590f515dc0a612e8fb65b33045c48ba56021b235b4750ee5`.
- The existing D05 baseline replay passed on the remote FT venv (`1 passed in 4.08s`) against the bd57 worktree. It is preserved as baseline only; under the strengthened rule it is not strict-completion evidence because its model-side callback assigns request lengths.
- The raw D09 target receipt pins observed `cached_tokens=20160`, but this observation is not a strict CPU reproduction.

A new strict replay cannot use the old `object.__new__(Scheduler)` seam. Direct source inspection of the pinned bd57 `Scheduler.__init__` shows unconditional `torch.cuda.Stream(device=self.device)` and `torch.cuda.set_stream(...)` before scheduler bookkeeping setup. With `CUDA_VISIBLE_DEVICES=''`, a real Scheduler constructor cannot be instantiated without monkeypatching CUDA scheduler initialization. That would replace product scheduler behavior beyond permitted token-model side effects.

Therefore neither strict actual output (13,376 and 20,160) exists. The required gate remains `UNREPRODUCED`; Q1–Q5 remain unanswered and no attribution or proposal follows.

## Raw hot event geometry

Read from SHA-bound `services/hot_c0_p20282_t1020/observations.jsonl`:

- UID 0: admission 0; layer-major prefill 0→20224; prefill 20224→20282 (58); continuation 20282→21302 (1020); then 32 decode tokens.
- UID 1: admission **20160**; restore-device source slot 10 to destination 12; prefill 20160→20224 (64); prefill 20224→20282 (58); continuation 20282→21302 (1020); then 32 decode tokens.

This is an evidence fact only. It does not yet identify the native event creating the UID 1 matched prefix.

## Raw state-dump binding

The SHA-bound hot `state_dump/index.jsonl` identifies the previously unknown source event: UID 0 recorded a `donate` at length **20160** (sequence 2, device slot 10), following its 20282 boundary record. UID 1 then recorded `resume-device` at 20160 from slot 10 to 12 (sequence 3). This binds the observed UID 1 admission to a real UID 0 native donation, but it does not yet prove the strict replay's matching code path.
