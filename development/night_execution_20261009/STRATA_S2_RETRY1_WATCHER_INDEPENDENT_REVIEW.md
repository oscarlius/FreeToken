# Independent watcher review — D09 T16 to Strata S2 retry-1

Remote review clock: `2026-10-10T00:50:39.731208+08:00`. Source SHA: `c0b573d545b30958ffd09e3bb9e972386ccc9ca0a4fd00cf52add95852553f99`.

## Verdict

**NOT_ADMISSIBLE_WATCHER_SOURCE. Do not permit this watcher to advance.**

The live watcher correctly remains dormant: its identity is `233227:165904836`, the exact D09 child is still active as `199552:165838035`, D09 reports `probing`, the GPU lock and compute PID remain present, and no cleanup, 8085 preflight, root admission, or S2 driver receipt exists. It does not require a D09 PASS verdict: it accepts only terminal `complete_measurements_pending_review` or `failed` and records `product_acceptance: false`.

It also correctly rebinds the v2 independent-review verdict, runner hash, R2 FILEdry hash, fresh FILEdry equality, S2's exact 3-service cap, and 11-call cap before launch.

Two source defects block admission. First, `Path.exists()` alone accepts a dangling `gpu.lock` or `production.active.json` symlink as absent. Both must require `not exists()` and `not is_symlink()`. Second, the cleanup loop checks each D09 owner PID/start-ticks/PGID but writes only `path`, SHA, and `absent: true`; it does not require a nonempty owner list. The immutable cleanup readback must retain each checked identity, PGID, port probe, and process/group-absence result.

This review did not run the watcher or create any cleanup, preflight, admission, service, GPU, HTTP, compilation, or model artifact.
