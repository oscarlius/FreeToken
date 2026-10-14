# Independent OOM Recovery Review — REQUEST CHANGES

- Reviewer: `/root/oom_independent_review`
- Reviewed at: 2026-10-14 Asia/Shanghai
- Product commit: `eb9e70f fix(server): retire oom request accounting before backend replacement`
- Scope: public OOM recovery source and private GPU-window controller/restore preparation.

## Verdict

**REQUEST CHANGES.** The public product accounting and daemon-failure repairs are acceptable on source review. The private controller remains blocked by two concrete defects below. No GPU, remote service, or production action was run by this review.

## Product review

`terminalize_oom_inflight` observes synthetic terminal acknowledgements before client delivery, so live and already-aborted UIDs leave `StatsTracker` accounting. `_on_failure` puts the non-shell daemon exit fallback in `finally`, so a failed lifecycle-loop transition cannot retain a serving API backed by dead workers.

Fresh CPU evidence was reported by the root lane as `cpu_fix_05: 1095 passed, 31 skipped`; the canonical rerun that includes the newly added aborted-UID regression was still pending when this artifact was written. This is CPU regression evidence only; it is not CUDA/OOM acceptance.

## Private-controller blockers

### [HIGH] Restoration reserve does not cover the controller's own cleanup/start time

File: `gpu_window_oom.py:19,234,286-289`

The controller reserves exactly 1,800 seconds, equal to the real adapter's readiness allowance. Candidate cleanup can still consume up to worker stop (120+30 seconds), GPU idle waiting (up to 120 seconds), and restore-start publication before `wait_release_and_smoke.py` begins. The outer 2,700-second deadline can therefore terminate a compliant 1,800-second restore waiter. The terminal is fail-closed, but it cannot claim completed restoration.

Fix: reserve the restore adapter's 1,800 seconds plus an explicit cleanup/start allowance, or use an approved restore adapter whose bounded limit fits the remaining window. The terminal must retain `failed_harness` and `restored: false` when this bound expires.

### [HIGH] Restore-package verification permits an empty adapter manifest and imports mutable controls

File: `gpu_window_oom.py:102-132`

`files = manifest.get("files") or {}` accepts `{}`. That skips all source-equality checks before importing `restore_e3/deploy_conditional.py` and root `recovery_guard.py`. A mutable package manifest can remove the adapter binding that the function claims to enforce.

Fix: require exactly the approved adapter set, require every file to be a regular non-symlink file, and compare copied `recovery_guard.py` with the frozen sibling source before importing it. Cover an empty/missing/extra manifest entry and a guard mismatch.

## Local review diagnostics

- `python -m unittest -v test_gpu_window_oom.py test_gpu_fault_probe.py`: **11 passed** at provisional review; **13 passed** after final hardening.
- `py_compile` for private controller/client/probe/hook/preparation files: **passed**.
- `git diff --check`: **passed**.
- No hard-coded secret, shell interpolation, or unguarded OOM injection was found in reviewed controller files.

## Hashes
- `fault_site\sitecustomize.py`: `cb055cdb31d3b4265af8cd031f49dd2bd8e6c54ecab38f0e33ede582cb30d11d`
- `gpu_fault_probe.py`: `b730880792e30d6eb50b098359d570a36560b78e0ed3ee88e4d386c79884a50d`
- `gpu_http_check.py`: `1dffb1dc996cebc7afcb6c2c554699886b6ea1fadc92548ae5c48380b60f0797`
- `gpu_window_oom.py`: `36928836fcbec6381a7938520b642b748e4becdf736a32905795a69e648abc22`
- `prepare_gpu_packet.py`: `817a7fa6b5ee33c8072819b82f1d0452852db66e20b79ea463cda76299fe8a85`
- `product/python/freetoken/server/api_server.py`: `76b217548d4ecb8c12c1113fc7a13413e7f4598593526e2c9cf29adda43431ed`
- `product/tests/server/test_oom_recovery.py`: `f85f09ce80bd046c7fc0d523f588ca5371f0ff1fd6e32e0d5695e106bae3a655`
- `recovery_guard.py`: `a7a743b300f63d59ad4de088394ed3fe33f3c7aa1fa771ca5ac44e26080d9a12`
- `restore_e3\SOURCE_MANIFEST.json`: `593216a51a5abf2d3cc6194139c88dcdb609d1cc9f73cb163ccf36125ba57986`

## Closeout — 2026-10-14 13:40 Asia/Shanghai

The two blockers above are resolved in the pinned final controller revision. This closeout supersedes the provisional **REQUEST CHANGES** verdict while preserving its review record.

### Remediated controller findings

- `gpu_window_oom.py:19,249` now reserves 2,100 seconds within the 2,700-second hard cap, leaving a bounded 600-second measurement period. If restoration exceeds the remaining cap, `run_command` terminates the waiter and the controller exits with `restored: false`; it does not report a successful restore. A detached restore supervisor may continue its own state transition, so this is an explicit failed-harness outcome requiring subsequent observation, not successful GPU evidence.
- `gpu_window_oom.py:106-142` now requires exactly six listed restore adapters, rejects symlinks, checks each copied adapter byte-for-byte against the frozen sibling, and checks copied `recovery_guard.py` before importing either mutable gate or guard code.
- `gpu_window_oom.py:308-334` recognizes an unchanged live original before idle waiting; the absent-pointer path proves idle and releases the owned D07 lock before starting the approved restore. This satisfies the real restore adapter's lock-absence precondition.

### Pin and test evidence

`WINDOW_PROPOSED.json` is inert (`authorized: false`, no independent-controller review) and pins the current controller, fault hook, copied restore adapters, recovery guard, baseline archive, and candidate archive. Its source pins match this review's current hashes.

`GPU_CPU_PREFLIGHT.json` records no production-control actions, CUDA hidden, private unit success, factory and engine hook installation, native/source-tree validation, and frozen-restore guard validation. It is preflight evidence only; it did not start a service or perform a GPU OOM run.

The candidate archive `candidate_eb9e70f.zip` has SHA-256 `cf184783a67f11282f0b5dc1457620136d4bb1c90991beff83072bdc7d09a592`. Its archived `api_server.py` and `test_oom_recovery.py` are line-equivalent to the reviewed `eb9e70f` product source (the raw bytes differ only from the Windows checkout line-ending representation). The remote CPU receipt reports  `1096 passed, 31 skipped, 2 warnings`, exit code zero, CUDA hidden, and production untouched.

### Final review position

**COMMENT — no unresolved source blocker.** The public patch and private controller are ready for the separately authorized GPU awareness window. This is not GPU/OOM acceptance, production restoration evidence, or a claim that the 600-second measurement period will complete on a particular host.

Final reviewed private hashes:

- `gpu_window_oom.py`: `36928836fcbec6381a7938520b642b748e4becdf736a32905795a69e648abc22`
- `gpu_http_check.py`: `1dffb1dc996cebc7afcb6c2c554699886b6ea1fadc92548ae5c48380b60f0797`
- `gpu_fault_probe.py`: `b730880792e30d6eb50b098359d570a36560b78e0ed3ee88e4d386c79884a50d`
- `fault_site/sitecustomize.py`: `cb055cdb31d3b4265af8cd031f49dd2bd8e6c54ecab38f0e33ede582cb30d11d`
- `prepare_gpu_packet.py`: `817a7fa6b5ee33c8072819b82f1d0452852db66e20b79ea463cda76299fe8a85`
- `recovery_guard.py`: `a7a743b300f63d59ad4de088394ed3fe33f3c7aa1fa771ca5ac44e26080d9a12`
- `restore_e3/SOURCE_MANIFEST.json`: `593216a51a5abf2d3cc6194139c88dcdb609d1cc9f73cb163ccf36125ba57986`
- `GPU_CPU_PREFLIGHT.json`: `1e11b6773baf56e8fb09c78a87d355d07a42445c39f14f739de0e0309e495f2f`
- `WINDOW_PROPOSED.json`: `5875bda0282f7e7458d1c7722bdea081aa2af949e6e28cb2fe356a74617686f1`


### Post-closeout controller pin update — 2026-10-14 13:42 Asia/Shanghai

The final controller adds `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` to the candidate-service environment. The former prevents Python bytecode writes into a sealed source tree; the latter makes service logs promptly observable. `py_compile` and `git diff --check` pass for this update.

Latest reviewed `gpu_window_oom.py` SHA-256: `9dbdb302060c6b41b6dcd994946a57c21c01d4dfc1e06180c86affe318a04e6d`.

At this instant `WINDOW_PROPOSED.json` remains inert and still carries the preceding controller hash `36928836fcbec6381a7938520b642b748e4becdf736a32905795a69e648abc22`; it must be regenerated and re-hashed to the value above before an authorization is derived. This is a pin-refresh prerequisite, not a product-source change.
