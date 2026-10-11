# D08/D10 retry2 static review

Reviewed: 2026-10-11T01:29:03.6002636+08:00

Verdict: **REQUEST_CHANGES**.

## Confirmed blocker

`d0_service.py:13-25` launches the newly added D0 GPU service without a self-source hash check. `gpu_window.py:144-145` accepts whatever `controller_source_pins` keys its admission supplies, so it does not require a D0 pin. Require the exact pin set and reject a missing or mismatched `d0_service.py` hash before creating output or spawning a process.

## Static checks that passed

- Hybrid argv, readiness/progress, private bounded two-request SDK warmup, input binding, and cleanup flow match the retry2 directive.
- D0 creates one fresh offload service and one lane-0 request; it rejects prior D0 rows and uses `steps * 480`.
- The controller retains a 45-minute global deadline and restores only after idle/no retained lock; failure with proven cleanup can continue to independent later arms as directed.
- Restore07 is identity-only against Restore06 for its twelve executable sources, and its approval scope/rollback identities now consistently use `-07`.

Existing `CPU_VALIDATION.json` reports 15 controller and 7 Restore07 CPU tests; it does not cover the missing D0 source-pin rejection.

