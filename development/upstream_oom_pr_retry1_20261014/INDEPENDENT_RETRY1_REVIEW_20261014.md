# Independent retry-window review — 2026-10-14

## Code Review Summary

**Files Reviewed:** 9  
**Total Issues:** 0

### By Severity

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

### Scope and result

This is a source-only review of the corrected, inert retry packet. It does not
claim GPU validation or product acceptance.

The first window is preserved as failure evidence: its terminal recorded a
`TimeoutExpired` from the `nvidia-smi --query-compute-apps` idle query after
`main` kept three calls; E3 restoration and its SDK smoke passed. The retry
removes `main` from execution and binds the two new arms to the hash-pinned
`reference_main_SUMMARY.json` baseline.

`wait_gpu_idle()` now treats only `subprocess.TimeoutExpired` and
`subprocess.CalledProcessError` as retryable query failures, records each with
`gpu_idle_query_retry`, and fails explicitly at the pre-existing absolute
idle deadline. It neither treats a failed query as idle nor suppresses the
final diagnostic.

The controller has a 3,600-second hard cap, 2,100-second restoration reserve,
and 1,500-second aggregate measurement deadline. It will not start another arm
after that measurement deadline. Candidate-off and candidate-on retain fixed
call caps of three and four, compare both canonical native-ID reference streams
with the sealed main baseline, and candidate-on continues to require one real
CUDA OOM, epoch transition, whole-old-worker retirement, request-accounting
closure, and preserved API identity.

The restore package enforces its new `...-02` identity, exact six-adapter set,
regular non-symlink byte-identical copies against the frozen source, and copied
recovery-guard identity before importing its gate. The recovery path releases
only its owned D07 lock before restore, preserves the no-duplicate-start branch
when the original owner is already live, and uses the new `...-02` approval for
its one restore and smoke.

### Verification

- `python -m py_compile gpu_window_oom.py gpu_http_check.py gpu_fault_probe.py fault_site/sitecustomize.py recovery_guard.py` — passed.
- `python -m unittest -v test_gpu_window_oom.py test_gpu_fault_probe.py` — passed, 17 tests.
- The tests cover transient `TimeoutExpired` and `CalledProcessError` followed by a valid idle result, absolute-deadline expiry, two-arm baseline matching, exact fault activation, factory epoch observation, partial-stop restoration, original-owner preservation, and restore-package/guard tamper rejection.

### Reviewed SHA-256 pins

| File | SHA-256 |
| --- | --- |
| `gpu_window_oom.py` | `7bac5cf5341521fcbd1cc839d06b3400d4490501906fce8588ce9873e5259844` |
| `gpu_http_check.py` | `1dffb1dc996cebc7afcb6c2c554699886b6ea1fadc92548ae5c48380b60f0797` |
| `gpu_fault_probe.py` | `b730880792e30d6eb50b098359d570a36560b78e0ed3ee88e4d386c79884a50d` |
| `fault_site/sitecustomize.py` | `cb055cdb31d3b4265af8cd031f49dd2bd8e6c54ecab38f0e33ede582cb30d11d` |
| `recovery_guard.py` | `a7a743b300f63d59ad4de088394ed3fe33f3c7aa1fa771ca5ac44e26080d9a12` |
| `test_gpu_window_oom.py` | `0e5f2f0752118648db2d95339c16b7ab3b060525a60c5874f0bb409de2af7a36` |
| `test_gpu_fault_probe.py` | `0c9b2767d96a61ade41571e12ee3a68dfdcc0104aed8980a3d2213aa95340e88` |
| `reference_main_SUMMARY.json` | `9db3854725671de0e801c34afa0f72f5080788c51894b6af2d876cf92d509279` |

### Sealing boundary

`WINDOW_PROPOSED.json` is correctly inert (`authorized: false`) at review time.
Before any user acknowledgement, root must generate the authorization from the
current packet, add the source SHA pins (including this review), bind the
external baseline fields, and run the existing sealed preflight. Those are
admission steps; they are not evidence of an executed GPU result.

### Recommendation

**APPROVE — source-only retry packet.** No unresolved source blocker was found.
