# R045 section 14 v9 readiness

`r045_d06_t05_prepare.py` now gates execution on the future sealed `E2-R040e` `measured` closure. It binds `E2-R040a`, `E2-R040c`, and `E2-R040d` only as failed-harness metadata. Those closures are explicit non-substitutes for the future gate: R040a retains six anchors and R040c retains six cases.

The performance T05 P1/P2 writer forces D0 and route trace off while keeping the 98,304-token window and memory ratio `0.88`. The D06 G3/G4 diagnostic remains separate: it retains the card-required D0 capture and the complete pause/cancel/resume chain. Physical token/output binding remains in the inherited G3/G4 and T05 client paths.

All v9 runtime copies use `shutil.copyfile` and immediately set mode `0600`. v9 dry-run/review schemas and paths reject v6/v7/v8 data.

Final Linux CPU evidence is `/data2/FreeToken/runs/dev_R045/r045_section14_v9_cpu_20261008_014711/report.json` (SHA-256 `3af3cee3dffb714c024f989a58d7d3443424d9b7d5acd7b7c10c5e17467af451`): 59 tests plus R045 and D06 CLI self-tests passed under the real CPU guard with `CUDA_VISIBLE_DEVICES=''`. Source is sealed `0555/0444`.

This is not a FILEdry, R review, future R040e closure, or GPU authorization. No service, request, GPU lock, batch, formal RID, or measurement was created.
