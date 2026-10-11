## Code Review Summary

**Scope:** R067e final retry2 CPU-only execution package.

**Files Reviewed:** 10
**Total Issues:** 2

### By Severity

- CRITICAL: 0
- HIGH: 2 (must fix)
- MEDIUM: 0
- LOW: 0

### Issues

[HIGH] The callable execution entry has no sealed-admission check and bypasses the parent owned lifecycle.

File: `retry2_runner.py:27`

Issue: `execute()` accepts only plan, batch, effects and run directory. At lines 34–37 it checks current source/donor values and invokes `r067e_actual.run_child()` directly. It never accepts or validates an admission document, requires neither the D07 reserved child receipt nor its process identity, and allows any supplied effect object. The actual parent admission and controller checks are in `../r067e_owned.py:92-97` and `:147-215`; they are not reached by this entry.

Impact: the claimed inert/root-sealed admission boundary is documentary only. A caller can reach the 10-service lifecycle without the required admission hash, candidate/engine/source pins, 10/14 budget declaration, owned process binding, lock lifecycle, runtime-source receipt or cleanup safety path. A CPU seam reproduction replaced `filedry` and `_actual`, passed batch 999 plus `object()` as effects, and observed `run_child` reached without an admission argument.

Fix: make the sole retry2 launch entry validate a retry2-specific, sealed admission document before any lifecycle effect. Bind it to retry2 RID, exact retry2 source manifest, parent packet SHA, worktree commit and engine SHA, input/schedule/adapter pins, batch and 10/14 budget. Then retain the parent controller/child semantics (reserved receipt, PID birth binding, owned cleanup and runtime source manifest), rather than calling `run_child` directly. Add negative CPU tests for absent/changed admission, changed source/packet/adapter hash, budget mismatch and an arbitrary effects object.

[HIGH] The new entrypoint cannot execute the required spawned route proof, and reports the unsupported probe as success.

File: `retry2_startup.py:54`

Issue: after importing the parent app, its `__main__` block sends every argument to `freetoken.cli.main()`. It does not forward `--cpu-startup-probe` to the parent startup's probe at `../r067e_startup.py:29-32`. Independent invocation of a materialized cold arm with its recorded environment and `CUDA_VISIBLE_DEVICES=''` returned exit code 0 with `unknown ft command: --cpu-startup-probe`; no multiprocessing child ran. `CPU_MATERIALIZE_RECEIPT.json` only reports copying 10 arms and explicitly reports `gpu=false`, `http=false`, `service_started=false`.

Impact: the package has no real CPU proof that the new wrapper is installed in the spawned interpreter and retains the pinned exact-ID POST route. The zero exit status can let a generic command-success check mistake an unsupported command for a valid proof.

Fix: implement an adapter-owned CPU probe that follows the actual spawn/import path for `r067e_retry2_startup.py`, verifies the exact-ID POST route and the adapter observer marker in the spawned child, asserts CUDA remains uninitialized, writes a bound receipt, and exits nonzero for every failure. Execute it with the materialized environment and add a regression test that rejects the current CLI fall-through.

### Evidence

- Remote CPU test: `CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /data2/FreeToken/venv/bin/python -m pytest -q test_retry2_execution.py` -> `2 passed in 1.73s`.
- Remote compile: `python -m py_compile retry2_execution.py retry2_effects.py retry2_runner.py retry2_startup.py` -> exit 0.
- These checks do not cover either blocker. The two tests cover digest labels and plan shape only.
- Input binding, 10-service/14-call plan construction, canonical label domain, materialized argv rewrite, and the pre-Engine-guard observer design were inspected. They are not sufficient to establish the sealed launch path or new-entrypoint spawn behavior.
- No GPU, service, API, lock, candidate source, parent source, or production artifact was changed in this review.

### Recommendation

REQUEST CHANGES

CPU only. This review neither launches nor approves R067e GPU execution; T17 and downstream gates remain outside scope.