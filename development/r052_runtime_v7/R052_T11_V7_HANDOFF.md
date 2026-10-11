# E2-R052a / T11 v7 local delivery

This is a new local closure.  Earlier v6 source, FILEdry, review, and CPU
artifacts remain historical evidence and are not reused as v7 evidence.

## Binding

The candidate remains `0aa23431e5b800797543bdecbf35a01045131d7d`; reverse
trace index 7, history UID 8, cache thresholds, D0/anchor evidence, private
ports, and owned lifecycle are unchanged.  `E2-R052a` additionally requires
the closed `E2-R052` `failed_harness` metadata, R041 kept, and T20's failed
harness.  The fixed R045 section 8.7 exception is unchanged and rejects a
formal directory or symlink.

The v7 dry receipt, startup review, owned-launch receipt, and raw result bind
these prerequisites using v7 schemas.  The default dry-run sibling and
startup-review path are v7-specific.

## Shutdown regression control

`r052_d0_shutdown_startup_v2.py` sends one `KeyboardInterrupt` for SIGTERM
after `Scheduler.run_forever` has started, then absorbs repeated SIGTERM until
the worker receipt is fsynced and the prior handler is restored.  Startup-time
SIGTERM and every other worker exception remain failures.  The preserved v1
wrapper is the failing control for the two-SIGTERM test.

## Remaining evidence

No v7 CPU-stage, FILEdry, startup-review, or formal-run evidence exists in
this local handoff.  Those are separate gates and no `--run`, service, lock,
batch, model port, GPU action, or measurement is authorized by this file.
