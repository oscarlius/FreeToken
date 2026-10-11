# Independent bd57 D09 CPU protocol review

**Verdict:** `PASS_CPU_PROTOCOL_REVIEW_NOT_GPU_AUTHORIZED`  
**Reviewed:** 2026-10-10T10:58:24.790974+08:00  
**Candidate:** `bd57cfdccc2a935d46cb0a89b8b36be7a18706de`

This independent review covers only `protocol_t16/`, `protocol_t17/`, `CURRENT_CPU_APPLICATION_MANIFEST.json` (`80e57684…`), and `CPU_LIFECYCLE_RECEIPT.json` (`a85410a1…`). The rejected simplified lifecycle prototype is excluded. This result grants no GPU-controller admission.

## Evidence checked

- Historical batch144 source count is bound to `/data2/_shared/runs/ft_rounds/E2-D09-T16-night-20261010-retry1/closure_evidence/full_protocol_count_review.json` (`48adea9d…`): 4 layer-major arms ×12 plus 4 ordinary arms ×13 = 100 generation POSTs. It corrects historical `96` metadata only and is not evidence that bd57 T16 passed.
- New T16 uses `E2-D09-T16-reapply-bd57-20261010`, plans 8/100 in the required 12/12/12/12/13/13/13/13 split, and retains `message_boundary_ckpt=False` as the only parsed candidate default delta. Parent/source/native bindings are preserved in the current manifest.
- New T17 uses `E2-D09-T17-reapply-bd57-20261010`, six services/eight calls, exact inputs (`b21a29e4…`), the copied exact-ID route/startup tooling, candidate/native pinning, donor-at-P boundary checks, and 768-page checks before any output judgment.
- T17 source requires a **new bd57** T16 sealed `kept` closure with exact round/manifest hashes and actual 8 services/100 generation calls. Old c17 T16 evidence cannot satisfy this gate.
- The server’s current package had all 260 manifest members present and hash-matching. Receipt-bound CPU e2e records show the controller-child/atomic-receipt path, task-owned fake lock release after cleanup, and no product acceptance. The 3 CUDA-hidden preflight tests passed; that light rerun does not replace the full CPU replay receipt.

## Admission boundary

`GPU_REAPPLICATION_PENDING.json` remains `PENDING_USER_GPU_APPROVAL`; no new controller admission exists. No GPU, service, HTTP request, lock action, build, or production action occurred during this review.

See [machine-readable review](INDEPENDENT_CPU_PROTOCOL_REVIEW_CURRENT.json).
