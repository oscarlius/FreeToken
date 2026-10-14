# Independent GPU Evidence Review — 2026-10-14

## Code Review Summary

**Files Reviewed:** 41 hash-bound downloaded evidence files, the retry-2 authorization, terminal, candidate receipt ledgers, native observer records, restoration receipts, and `PR_BODY.md`.

**Total Issues:** 0

### By Severity

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

### Evidence verdict

**PASS.** `GPU_WINDOW_TERMINAL.json` is `kept` with one `candidate_on` arm, four calls, and `restored: true`. I recomputed all 41 payload SHA-256 values from `DOWNLOAD_MANIFEST.json`; every value matches. The downloaded-manifest SHA-256 is `b39c663fb3e53fab29d1a2886d2fcbdc5faa266942f196a73ce78ff900eeaa78`.

The authorization pins final candidate `a4ebbfda742fbad1df240621647014a39c70acd6` to `candidate_oom_final.zip` SHA-256 `4a7eba0bf148ce7b3c5e78168971ccc356b20b1accccfe2165f92c2b3a195a8c`; that equals the locally retained archive and the candidate CPU receipt. It also pins the preceding independent source review (`5c57e169d7150e6b3cf1734f10aa98164fa5b540333a9ee828d18031c78577db`).

The private hook recorded one actual `OutOfMemoryError` from an allocation above total VRAM at UID 1, epoch 0, step 9. Its raw SSE contains exactly one `worker_restarting_after_cuda_oom`, one `insufficient_workspace` code, and one `[DONE]`, with no ordinary stop or length terminal. The fault is therefore terminalized once rather than replayed.

`backend_handles.jsonl` records the same API PID/start ticks (`468984` / `205706807`) across epochs 0 and 1. Epoch-0 workers `469270,469271` and epoch-1 workers `483507,483508` are disjoint; the pinned client performs the old-dead/new-live birth-identity checks before accepting its summary.

The four authorized requests are one initial `short512`, the fault stream, `queued512`, and post-recovery `long8257`. The three successful receipt rows have unique request IDs, UID sequence 0/2/3, zero cached tokens, length finish, and 128 native IDs. The summary's queued/post-recovery references match the frozen main reference for both 512 and 8257 prompts. Final stats show `active: 0`, `completed: 4`.

E3-03 restoration is also hash-bound and complete. `production.active.json` and E3-03 `owner.json` agree; the official-SDK smoke finished exit 0 with classification `passed`, executing the approved 512- and 8257-token prompts with 128 output tokens each.

### PR-body review

`PR_BODY.md` correctly limits the GPU statement to one RTX 4090/raw-completions round, says that the other public protocols have CPU coverage, excludes both earlier `failed_harness` rounds from the passing claim, and makes no throughput or multi-GPU claim. Its raw error-code statement is directly supported by the final two serializer branches and their HTTP tests.

### Recommendation

**APPROVE publication of the reviewed contribution.** This verdict covers the final candidate and the bounded evidence above. It does not expand GPU acceptance beyond that one target-model, raw-completions recovery round.
