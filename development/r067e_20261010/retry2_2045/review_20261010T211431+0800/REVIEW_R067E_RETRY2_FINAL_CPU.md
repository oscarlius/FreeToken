## Code Review Summary

**Files Reviewed:** 5 source/test files plus the final freeze declaration
**Total Issues:** 2

### By Severity

- CRITICAL: 0
- HIGH: 2 (must fix)
- MEDIUM: 0
- LOW: 0

### Issues

[HIGH] The sealed R067e admission trusts an unsealed, mutable T17 raw terminal.

File: `retry2_runner.py:94`

Issue: `validate_sealed_admission()` only checks that the terminal is a file and its JSON field `proposed_verdict` is `failed_harness`. It does not require a terminal hash/sidecar, read-only regular-file mode, no symlink, a formal closed round, or a manifest binding. The actual remote terminal was independently observed as a normal writable file (`0664`) beneath writable (`0775`) directories, with no `.sha256` sidecar. The test fixture confirms the behavior: it writes a writable bare terminal then successfully calls `validate_sealed_admission()` at `test_retry2_execution.py:31-46,80`.

Impact: a sealed retry admission can be formed against a mutable predecessor carrier. It also cannot bind the independent formal T17 closure (including its independently determined outcome) that is required before R067e proceeds.

Fix: have the root admission declare the closed T17 round, manifest, terminal and their exact hashes. Validate each through the same non-symlink/read-only/hash-checked mechanism, validate the T17 RID and formal verdict/result, and reject the raw unclosed carrier. Add negative tests for writable terminal, missing/changed sidecar, wrong terminal hash, and wrong closed-round verdict.

[HIGH] The claimed spawn/materialization evidence is from the pre-fix adapter, so it cannot validate this freeze’s corrected startup path.

File: `FINAL_CPU_FREEZE_20261010T212100+0800.json:10-16`; evidence `cpu_materialize_v4/CPU_SPAWN_PROBE_RECEIPT.json`

Issue: the final freeze pins `retry2_runner.py` to `2d70138…` and `retry2_startup.py` to `0c25c18…`; the existing CPU spawn receipt and its materialized wrapper bind the earlier `967e404…` runner and `66924b…` startup. Its materialized environment also records `CUDA_VISIBLE_DEVICES=0`, rather than the required hidden-CUDA CPU proof environment.

Impact: the receipt cannot establish that the final controller routing or “parent pin before adapter observer” behavior was exercised. Passing six unit tests and compiling do not replace an execution proof for the changed entrypoint.

Fix: create a new task-owned CPU-only materialization/spawn artifact for the final frozen hashes, execute it with `CUDA_VISIBLE_DEVICES=''`, and bind the wrapper hash, source manifest, argv, route presence, observer marker, and `torch.cuda.is_initialized()==False`. Re-run independently after it is generated.

### Evidence

- Fresh remote verification: final declaration SHA-256 `c3d1fc0cd9c76f66c2ec40a7a66fdf2f335ebc86edc298954d86ed17a5ffdfc0`; all five frozen source/test hashes matched remote.
- Fresh remote CPU command: `CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /data2/FreeToken/venv/bin/python -m pytest -q …/test_retry2_execution.py` → `6 passed in 1.42s`; `py_compile` returned 0.
- Controller route is now correct: `retry2_runner.py:113-117` calls `r067e_owned.controller`; `:123-141` validates the issued receipt before `r067e_owned.child`. This finding is closed from the prior review.
- No GPU, service, HTTP, lock, or product source action was performed by this review.

### Recommendation

REQUEST CHANGES
