# R045 v16 CPU/source readiness review — 2026-10-08

## Scope

Read-only review of `r045_section14_draft_v16/source/r045_d06_t05_prepare.py` and its sealed Linux CPU package. This is not a FILEdry review, startup signature, GPU launch authorization, or T05/D06 acceptance.

## Evidence verified

- Linux stage `/data2/FreeToken/runs/dev_T05/r045_section14_v16_cpu_20261008_064400` is `0555`; `report.json` is `0444` and SHA-256 `b7c97773a79b43909f6e7b6f223d913920b95f6332b11fd8e33ba1e7a05034ef`.
- The report records `86` passed, empty CUDA visibility, denied socket operations, and no formal round, lock, or service.
- The source manifest is `0444`, SHA-256 `049ea8bd59138321ac85f1c3c335db0e9ae4dee3ea99132c8ef68580ac01171f`.
- Actual metadata-reader/checker tests passed for R040, R040a, R040c, R040d, R041-gate-D17, and R055b. The required measured predecessor `E2-R040f` remains unsatisfied.

## Source conclusions

- The v16 runtime requires sealed `E2-R040f` measured and retains earlier D16/T20/R055 failures as metadata; it does not treat them as performance success.
- `source_hashes()` binds the entry, ordinary client/adapter/startup closure, D06/D07 readers, immutable checker, pause sources, parser, candidate probe, and raw cold helpers. Archive copies preserve those identities.
- Performance T05 executes ordinary SSE with D0, pause, and route trace disabled. H1/SC5 is an explicitly separate diagnostic service with D0/pause enabled and marked as non-reusable performance evidence.
- SC5 binds each of three repetitions to a distinct two-UID diagnostic step/timeline tuple and validates finite per-layer copy/compute fields. The final timeline SHA is computed only after owned-service stop.
- The dry writer produces per-arm/per-diagnostic output probes and records all service-start/request/lock/formal-round flags as false; its v16 receipt is revalidated before any controller path.

## Result

**CPU/source-ready only.** No issue found in the reviewed closure. R040f must first close measured; then same-entry FILEdry and an independent startup review remain mandatory.
