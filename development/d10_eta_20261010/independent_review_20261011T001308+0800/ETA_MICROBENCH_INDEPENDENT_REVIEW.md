## Code Review Summary

**Files Reviewed:** 3
**Total Issues:** 6

### By Severity

- CRITICAL: 0 (must fix)
- HIGH: 4 (should fix)
- MEDIUM: 1 (consider fixing)
- LOW: 1 (optional)

### Issues

[HIGH] `id_of_slot` values are expert IDs, not slot indices. `eta_microbench.py:81-84,117-120` can select a graph-used destination slot. Return occupied indices, assert disjointness, and regress with IDs different from positions.

[HIGH] No all-hit receipt exists after warmup. `eta_microbench.py:114-129` must fail closed unless every fixed graph-route expert is resident before samples.

[HIGH] Preregistered geometry is not proved. `eta_microbench.py:112-126,144-148` must require 2200 free slots and validate/report 367 × 2772480 bytes.

[HIGH] Concurrent compute slowdown is recorded but not calculated. `eta_microbench.py:131-149` must emit the percentage required by directive line 83.

[MEDIUM] GPU execution does not require the pinned X input. `eta_microbench.py:174,193-195` should require `--input-x` and record its verified SHA.

[LOW] Unused `PROTECTED_GRAPH_SLOTS` constant at `eta_microbench.py:10`.

### Verification

`python -m pytest -q development/d10_eta_20261010/test_eta_microbench.py`: 6 passed in 0.23s. This was CPU-only and does not validate graph/copy behavior.

### Recommendation

REQUEST CHANGES. No GPU run is approved at source SHA `98194aa6...`. Full evidence is in `ETA_MICROBENCH_INDEPENDENT_REVIEW.json`.
