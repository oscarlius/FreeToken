# D15 Stage 0b lag-one final CPU non-author review

- Reviewed at: 2026-10-10 20:03:18 +08:00
- Candidate: 7eba574a740217e0a61f46cf3cb432612bbacadf
- Base: 825655305d69df94d3d2f79c3f416234bfe890e6
- Scope: CPU-only source/protocol/test review. No GPU, T21, download, build, push, production-tree change, CUDA ordering proof, or output-equivalence claim.

## Code Review Summary

**Files Reviewed:** 8 (6 changed files and the two relevant runtime dependencies: offload_kernels.py and ngine.py)
**Total Issues:** 0

### By Severity

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

### Spec compliance and root-cause review

- Default FT_DEV_EXPERT_POLICY=lru preserves its public statistics schema and creates no lag-one stream or transfer counter. The legacy tensor regression and graph-capture parameterization cover the default/off combinations.
- Lag-one remains opt-in. It stages into private mpty_like rows; enqueue leaves live rows and both maps untouched. A pending staging event must query complete at a strictly later scheduler boundary before publication.
- The earlier raw-miss defect is repaired. ecord_expert_policy_routes scopes protection to the scheduler boundary epoch, while nsure_experts adds the post-native-LRU slot assignment. The raw-miss regression monkeypatches only the native lru_ensure primitive, then invokes the real cache wrapper, proof, and publish path. A conflicting pending transaction is discarded without live-row or map publication.
- The earlier historical-union defect is repaired. Protection resets when the scheduler-boundary sequence changes, rather than following the per-layer LRU clock; the two-layer regression proves union within a step and reset at the next boundary.
- Stable victims exclude volatile [0, 2E) slots. The current code fences the staging-to-live D2D copy before map writes, and fences publication/rollback work. CPU coverage proves state-machine behavior only; CUDA stream execution is explicitly unvalidated.
- D0 receipts contain scheduler boundary step, independent LRU clock, layer, expert, slot, bytes, enqueue timing, observed completion, publication time, and CUDA elapsed field. CPU values label CUDA elapsed as None; CPU wall-clock is not presented as GPU completion. D0-off avoids per-swap receipt/timing-event construction. Synchronous PA now records the same identity/cost fields and fences its live copies before map mutation.
- Enabled lag-one adaptation disables CUDA graph capture so host-side post-allocation protection cannot be skipped by replay. The actual engine initialization passes the cache to GraphRunner.
- No secret, injection, silent-fallback, or failure-masking pattern was introduced. Copy/publish failures retain explicit rollback/lock behavior.

### Validation

- Local worktree: clean at the candidate SHA; git diff --check passed.
- Remote dedicated worktree: clean at the same SHA; git diff --check passed.
- Independent remote target CPU command with CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS=1, and MKL_NUM_THREADS=1: **49 passed in 3.16s**.
- Local py_compile passed for all changed Python production and test files.
- Final recorded full CPU suite evidence: **83 passed, 103 skipped, 3 failed in 3.88s**. The only failures remain the 825 baseline's Global context is not set cases at 	ests/moe/test_offload.py:113,199,373; no candidate-specific failure was added.

### Recommendation

**ACCEPTED_CPU_SCOPE.** This admits only the Stage 0b CPU protocol and regression scope. CUDA auxiliary-stream event ordering, GPU event durations, graph/eager runtime behavior, token equivalence, and T21 remain unvalidated GPU gates.
