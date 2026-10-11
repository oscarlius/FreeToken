# Tail owned-exit read-only audit — 2026-10-08

Scope is limited to current entries named in `current_execution_state`: R045 v15, R048 v7, R052 v5, R044 v5, and R047 v10. I read only the entry/source locations and the FTD/README pointers. No service, listener, GPU, lock, or source mutation occurred.

## Result

No instance of the T21 v12 `try: return ...; else: release_gpu_lock(...)` success-path lock leak was found in the five current entries. In each actual child/body path, release follows completed owned-process cleanup; cleanup failure preserves the lock.

| Entry | Current source and evidence | Exit-path result |
|---|---|---|
| R045 v15 | `development/r045_section14_draft_v15/source/r045_d06_t05_prepare.py:511-549` | The outer `finally` stops any active owned process, preserves the lock on a cleanup failure or surviving process group, then unlocks and writes `owned_cleanup.json`. Per-arm service cleanup is in `:524-534`; no early successful return bypasses the outer finalizer. |
| R048 v7 | `development/r048_t09_prepare_v7.py:412-454`, `:476-496` | `run_measurements` stops each phase service in its `finally` (`:427-432`). `child` releases only after successful return; its error branch releases only when `owned_cleanup_failed` is false. `stop_service` marks cleanup failures and verifies the owned group is gone (`:216-226`). File-dry returns no process and never reaches child lock acquisition. |
| R052 v5 | `/data2/FreeToken/runs/dev_R052/runtime_cpu_v5_20261007_175017/development/r052_t11_followup_prepare.py:68-99` | `run_owned_body` always enters `finally`, stops the recorded process, checks group liveness, preserves the lock on either cleanup failure, and releases only after confirmed cleanup. The post-cleanup D0/result validation is intentionally after release (`:92-99`); it has no live service to orphan. Service-start failure cleanup is also guarded in `r052_t11_replay.py:198-225`. |
| R044 v5 | `/data2/FreeToken/runs/dev_T10/r044_runtime_v5_cpu_stage_20261007_1826/development/t10_e2_r044_prepare.py:314-349` | The v5 body tracks `cleanup_failed`; its finalizer stops a remaining owned process, preserves lock on failure/alive group, otherwise releases (`:343-349`). No return appears inside the guarded region. |
| R047 v10 | `development/r047_runtime_v10/r047_prepare_v10.py:600-725` | `_run_arms` stops the process after each arm and retries in its `finally` if still active (`:613-652`). `child_execute` sets `release=False` when cleanup is indeterminate or the group remains alive, then conditionally releases at `:695-725`. |

## CPU / FILEdry consistency

R048's `prepare()` calls the same `run_measurements(..., file_dry_run=True)` scheduling loop (`r048_t09_prepare_v7.py:454-475`), but `start_service` returns before `Popen` and writers are probes (`:231-239`). R045/R052/R044/R047 file-only paths remain separate no-service branches as declared by their current FTD state; none claims a GPU lock or service start during CPU/file-only runs.

## Minimal regression gap

No code change is recommended. The only useful additional regression would be a parameterized lifecycle test for each entry that forces a *successful* body completion with a live owned process and asserts lock preservation. Existing code checks group liveness, but that exact cross-entry success-path scenario is not established by this read-only audit.
