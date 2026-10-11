# T17 v6 rebind-safety implementation handoff

- Scope: `d09_t17_runner_v6.py` and `test_d09_t17_runner_v6.py`.
- Runner SHA-256: `1f9bca11c8005dbf5de4d92223b01a5fbdb4630f7defb183129907ada052ee5e`.
- Prior v5 bytes remain preserved. This document is not an independent approval.

## P0 repair

The child no longer infers unsafe cleanup by searching exception text. Both the live service path and injected FILEdry path wrap every post-stop two-port reserve/release failure in `PostCleanupRebindFailure`. The child catches that explicit type, marks cleanup unsafe, leaves the D07 lock in place, writes `unsafe_cleanup.json` with `outcome: failed_harness`, `post_cleanup_closed: false`, and `product_acceptance: false`, then exits nonzero. A closed `terminal.json` is only written after successful cleanup and lock release.

## CPU evidence

- `python d09_t17_runner_v6.py --filedry` completed the controller/child fake chain: sealed T16 `kept` + manifest binding, atomic receipt, six fake child processes, eight fake transports, six pair-rebind receipts, and released task-owned lock.
- `python -m pytest -q test_d09_t17_runner_v6.py` reports `2 passed`.
- The exception test injects the actual value `OSError(98, 'Address already in use')`; it verifies a retained task lock, `unsafe_cleanup.json` marked `failed_harness`, and absence of both run terminal and E2E closed terminal.

No GPU, service, HTTP, compilation, or JIT action was performed. Independent review and root admission remain required.
