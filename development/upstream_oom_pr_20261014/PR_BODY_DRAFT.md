Runtime CUDA OOM currently kills backend workers and leaves recovery to the outer daemon. This adds opt-in `--oom-recovery` to retire and reap the failed backend group, start a fresh group, and preserve the API process.

Dispatched requests receive a terminal retryable error once and are never replayed. New requests may wait in a bounded admission queue until replacement readiness. Backend epochs reject stale input/output traffic, including aborts and cache-rebuild controls. Shutdown wins over recovery; failures outside a typed, post-ready CUDA OOM retain the existing daemon fallback. The feature defaults off.

Validation against upstream `f02fbb1`, candidate `eb9e70f`:

- Linux CPU regression: **1096 passed, 31 skipped**, covering server, tokenizer, daemon, scheduler and KV cache. Frozen upstream baseline: 1073 passed, the same 31 skipped.
- Tests cover bounded/cancellable admission, replacement limits/readiness, old-process cleanup, epoch isolation, stop/rebuild races, terminal accounting for disconnected clients, wire messages and all four public generation routes with a CPU backend.
- Native modules were rebuilt from the frozen upstream base in an isolated dependency-conformant environment; all imports passed. No production dependency changes.
- **GPU acceptance pending.** A bounded target-model runtime-OOM test and independent evidence review will be recorded before publishing this PR.

This contains only OOM lifecycle recovery and its tests/documentation. It makes no throughput claim and does not change allocation sizing, prefill algorithms or expert-cache policy. Related: #110, #172.
