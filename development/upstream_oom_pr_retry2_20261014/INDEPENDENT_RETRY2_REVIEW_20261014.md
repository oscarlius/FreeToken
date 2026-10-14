# Independent Retry-2 Source and Admission Review — 2026-10-14

## Code Review Summary

**Files Reviewed:** 18
**Total Issues:** 0

### By Severity

- CRITICAL: 0 (must fix)
- HIGH: 0 (should fix)
- MEDIUM: 0 (consider fixing)
- LOW: 0 (optional)

### Scope and verdict

**APPROVE — source and admission only.** This is not GPU acceptance and does not change the preserved `failed_harness` classification of the earlier windows. The packet remains inert: `WINDOW_PROPOSED.json` has `authorized: false`, no `WINDOW_AUTHORIZATION.json` exists in this packet, and no controller was started during this review.

The reviewed candidate is `a4ebbfda742fbad1df240621647014a39c70acd6`. The final delta carries `UserReply.error_code` through both raw `/v1/completions` terminal serializers:

- `python/freetoken/server/openai_api.py`: SHA-256 `c734069a38baafe30b63d39b29271aea0b5882efcc57d9662497403e18c8aad7`
- `tests/server/test_openai_api.py`: SHA-256 `fbb72954357a8a3298a89d6c8c9ec6bcdf6b4a56f33cdaea2db81b9dd5e93d7c`

The two new HTTP-route tests cover a non-stream terminal and a streaming partial response followed by exactly one coded OOM terminal and `[DONE]`. They repair the observed wire contract directly; they do not introduce a fallback or suppress an error.

The candidate receipt records the intended Linux CPU command with `CUDA_VISIBLE_DEVICES=''`: **1098 passed, 31 skipped**, exit 0, against `candidate_oom_final` archive SHA-256 `4a7eba0bf148ce7b3c5e78168971ccc356b20b1accccfe2165f92c2b3a195a8c`. This is CPU evidence only.

### Retry-2 admission checks

- `gpu_window_oom.py` restricts execution to `ARMS = ("candidate_on",)` and `CALL_CAPS = {"candidate_on": 4}`. The controller verifies the emitted summary has exactly four calls and compares the two 128-token native-ID references to the hash-pinned, previously collected main reference; it does not rerun a main or candidate-off arm.
- The controller records a typed OOM terminal only when both the code `insufficient_workspace` and message `worker_restarting_after_cuda_oom` are received. It also requires one real CUDA allocation exception at epoch 0/UID 1, worker generations 0 then 1, old-worker retirement, stable API identity, queued-request correctness, post-recovery long generation, and `active == 0`, `completed == 4` accounting.
- The 3,600-second hard cap reserves 2,100 seconds for restoration and limits measurement to 1,500 seconds. Readiness and `nvidia-smi` probes have bounded deadlines; `TimeoutExpired` and `CalledProcessError` are recorded and retried only until the absolute deadline, then produce a visible failure.
- Before stopping the active E3-02 owner, the controller verifies every pinned file, both source archives/trees and native allowlist, the source-bound six-adapter non-symlink restoration package, copied `recovery_guard.py`, the current owner identity, and the frozen restore admission. It releases its owned D07 lock before starting E3-03. Foreign/stale active ownership fails closed; a partial stop with no active pointer enters the guarded restore path.
- The proposed scope is one candidate service, four generation calls, at most two pending HTTP requests, one backend replacement, one E3-03 restoration service, and two restoration SDK calls. The active snapshot remains exact E3-02 identity; the new restore identity is `UPSTREAM-OOM-PR-RESTORE-E3-20261014-03`.

### Diagnostics and verification

- Fresh local private controller/fault suite: **17 passed** (`test_gpu_window_oom.py`, `test_gpu_fault_probe.py`).
- Fresh `py_compile` passed for controller, client, fault hook, recovery guard, sealing script, and restore adapters.
- Recomputed retry-2 restore adapter hashes against the frozen source: no mismatches; all required adapter files are regular, non-symlink files.
- `GPU_CPU_PREFLIGHT.json` independently records the same 17 private tests, source/native verification, restore-package verification, CUDA hidden, and `production_control_actions: 0`.
- `git diff --check eb9e70f..a4ebbfda742fbad1df240621647014a39c70acd6` is clean; the product checkout is clean at review time.

### Issues

None.

### Recommendation

**APPROVE** for sealing and requesting the separate user authorization for the bounded retry-2 window. The sealing action must add this artifact's SHA-256 to the authorization pins, as `seal_window.py` is designed to do. A future GPU result may be called a full GPU pass only after its terminal artifact shows the four-call candidate-on sequence and successful E3-03 restoration with the two approved SDK calls.
