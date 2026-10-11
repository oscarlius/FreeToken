# D08/D10 re-review after controller fixes

Result: **REQUEST_CHANGES — one remaining HIGH**.

The earlier restore deadline, birth fallback, and auto max-fetch findings are addressed in current source: restoration helpers receive an absolute deadline and use private-session bounded termination; `capture_birth` provides a Popen-child/OS-session fallback and cleanup retries it; auto fetch now requires parseable branch semantics and writes a normalized value/fraction.

## HIGH: initial production stop remains unbounded

`gpu_window.py:152` calls `subprocess.run([..., stop_approved_restore.py], ...)` without `timeout` or the new private-group bounded helper. It occurs after the 90-second offload measurement and before eta/hybrid, inside the directive’s single ≤2100-second window. A hung initial stop can therefore run past the global deadline before any restoration reserve logic runs.

Required correction: route this initial stop through the same proof-bound `bounded_restore_command` (or equivalent) with an explicit absolute-deadline budget and test its timeout/private-group path. The controller must retain enough time for recovery/restore or fail closed before the remaining budget is consumed.

## Verification

`python -m pytest development/d08_d10_gpu_window_20261011/test_hybrid_service.py development/d08_d10_gpu_window_20261011/test_window_measure.py -q` → `8 passed in 0.22s`.

No GPU, process, lock, or source-controller mutation was performed by this review.
