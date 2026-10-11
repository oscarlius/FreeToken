# D15 Stage 0b lag-one CPU non-author review

- Reviewed at: 2026-10-10 19:37:18 +08:00
- Candidate: 11de101b43320709bb5e51a8556d46cb6d4f638
- Base reviewed: 825655305d69df94d3d2f79c3f416234bfe890e6
- Scope: CPU-only code and regression review. No GPU, T21, download, build, push, production-tree modification, or token-equivalence claim.

## Code Review Summary

**Files Reviewed:** 6 (the 5 changed files plus python/freetoken/moe/offload_kernels.py, which determines the relevant cache mutation order)
**Total Issues:** 4

### By Severity

- CRITICAL: 0
- HIGH: 1 (must fix)
- MEDIUM: 1 (should fix)
- LOW: 2 (optional)

### Spec coverage established by inspection

- The LRU default remains conditionally inert: the auxiliary stream is constructed only for profile+adapt, lag-one opt-in, and CUDA; the default-LRU regression compares legacy tensors and verifies no auxiliary stream.
- Lag-one enqueue writes only private cloned staging rows and leaves live rows/maps untouched. Publication requires a later proof and a completed staging event. The current scheduler-stream wait_event, same-stream D2D writes/maps, and terminal fence form the intended CUDA ordering, but CPU evidence does not prove it.
- Publish and rollback take row/map snapshots and fence their CUDA work. The D0 record distinguishes enqueue wall-clock fields from copy_completion_observed_at; CUDA duration is recorded from CUDA timing events.

### Issues

[HIGH] Current-step raw cache misses can still claim a pending adaptation victim, after which publication overwrites a slot used by that step.

File: python/freetoken/moe/offload_cache.py:883-891, python/freetoken/moe/offload_cache.py:1829-1841, python/freetoken/moe/offload_kernels.py:31-43, python/freetoken/moe/offload_cache.py:1138-1165

Issue: Protection is computed before lru_ensure. For a raw miss, slot_for_id returns -1, so no slot is inserted in _adaptation_protected_slots. The subsequent existing LRU primitive can allocate that miss into the pending victim; it has no awareness of the pending reservation. Publication only tests the pre-ensure set and can then replace the current step's top-k slot. This violates Stage 0b's no-current-step-top-k-overwrite requirement.

Fix: Keep a pending-victim reservation through the LRU allocation or update the pending protection from the actual post-ensure slot assignment before the next boundary. On conflict, discard the pending transaction before live-row/map writes. Add a CPU regression that monkeypatches only the lowest-level lru_ensure primitive with the calibrated CPU slot-assignment mirror while exercising the real OffloadMoeCache.ensure_experts, proof, and publish methods. Label it as a CPU primitive stub, not CUDA-kernel proof.

[MEDIUM] Protected slots are not step-scoped when adaptation is scheduled less frequently than every boundary.

File: python/freetoken/moe/offload_cache.py:889-891, python/freetoken/moe/offload_cache.py:1105-1108, python/freetoken/moe/offload_cache.py:1008-1038

Issue: _adaptation_protected_slots grows on every route recording and is cleared only after a successful enqueue. With FT_DEV_EXPERT_ADAPT_EVERY > 1, scheduled boundaries retain historic top-k slots until the eventual enqueue. This is conservative for safety but makes the victim plan depend on prior steps rather than the producing step and can eliminate all otherwise eligible stable victims.

Fix: Define the set's boundary scope explicitly. Reset historical protection before collecting a new producing step, while retaining a separate pending-transaction reservation/guard for the following step. Add a regression using ADAPT_EVERY > 1 to show old protections no longer suppress a later current-step plan.

[LOW] D0 regression checks timestamps but does not prove the receipt identity and byte-count fields.

File: 	ests/moe/test_expert_profile.py:560-577

Issue: The test asserts status and timestamp order but not exact step, oundary_seq, layer, xpert, slot, or ytes. A field mix-up would pass this regression.

Fix: Assert the expected transaction identity and byte sum before/after publication, and assert CPU receipt cuda_copy_elapsed_ms is None. Keep CUDA timing as an explicitly unverified GPU gate.

[LOW] A stale method docstring still states that live cache planning always requires D17.

File: python/freetoken/moe/offload_cache.py:989-996

Issue: The implementation now accepts the registered scheduler-owned runtime proof, and project documentation describes that path. The old text is inaccurate and has already caused review confusion.

Fix: Replace it with the actual proof/stream requirements and retain the separate statement that CPU fixtures do not prove CUDA ordering.

### Validation

- Local candidate: clean at 11de101b43320709bb5e51a8556d46cb6d4f638.
- Remote dedicated worktree: clean at the same SHA.
- Independent target CPU command (hidden CUDA, OMP_NUM_THREADS=1, MKL_NUM_THREADS=1): **43 passed in 3.39s**.
- py_compile passed for both changed Python production files and the changed regression file.
- Independent full 	ests/moe CPU run: **77 passed, 103 skipped, 3 failed in 3.71s**. The three failures are the pre-existing Global context is not set fixture failures at 	ests/moe/test_offload.py:113,199,373; no new failure was observed.
- Direct CPU execution of native lru_ensure is unavailable because it is a Triton GPU primitive, so the raw-miss-to-victim case has no current CPU behavioral regression. This gap supports the HIGH finding; it does not establish CUDA behavior.

### Recommendation

**REQUEST CHANGES.** The raw-miss path must be guarded and tested before Stage 0b CPU admission. Even after it is corrected, this review can only approve the CPU protocol; CUDA ordering, real event timing, output equivalence, and T21 remain unrun gates.
