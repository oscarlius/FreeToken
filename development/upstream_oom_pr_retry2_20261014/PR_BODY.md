Runtime CUDA OOM currently terminates backend workers and leaves recovery to the outer daemon. This adds opt-in `--oom-recovery` to retire and reap the failed backend group, start a fresh group, and preserve the API process. The default remains off.

Dispatched requests receive one explicit terminal error and are never replayed. New requests may wait in a bounded admission queue until replacement readiness. Restart attempts and readiness are bounded; backend epochs reject stale requests, replies, aborts and cache-rebuild controls. Shutdown takes precedence and other failures retain the daemon fallback. Raw completion responses now preserve backend error codes in both streaming and non-streaming responses.

Validation against upstream `f02fbb1`, final candidate `a4ebbfd`:

- Linux CPU regression: **1098 passed, 31 skipped** across server, tokenizer, daemon, scheduler and KV cache. Frozen upstream baseline: 1073 passed with the same 31 skipped. Tests include all four public generation adapters, admission/stop/rebuild races, process cleanup, epoch isolation and terminal accounting for disconnected clients.
- Target-model test on one RTX 4090 with Qwen3.8-Flash-Next-NVFP4: after eight successful forwards, a private hook attempted an allocation larger than total VRAM and recorded a real `torch.cuda.OutOfMemoryError`. The failed stream emitted `insufficient_workspace` and `[DONE]`.
- Final candidate's four-call recovery round passed: API PID/birth identity remained unchanged, old workers were gone and replacement workers were live; a queued 512-token request and a post-recovery 8257-token request each generated 128 native token IDs identical to frozen upstream references. Final accounting was active=0/completed=4.
- Default-off GPU reference checks passed at parent `eb9e70f`; subsequent product changes only preserve raw error-code serialization. The final revision has fresh CPU coverage and the full enabled recovery test above. Source and GPU evidence received independent review before publication.

Earlier validation rounds remain recorded as `failed_harness`: one stopped on a transient GPU-query timeout; another exposed the missing raw-completion error code and stopped before its remaining assertions. They are not counted as passing recovery rounds. Private fault hooks and host-specific validation controls are excluded from this PR.

GPU coverage is limited to one GPU and raw completions; other protocol adapters have CPU coverage. This changes OOM lifecycle recovery, not allocation sizing, prefill algorithms or cache policy, and makes no throughput or multi-GPU claim. Related: #110, #172.
