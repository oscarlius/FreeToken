# R045 v14 targeted runtime review — 2026-10-08

## Scope and CPU evidence

This read-only review covers only the v14 changes that close the two v13
findings: cross-repetition SC5 reuse and pre-stop D02 artifact hashes. Linux
CPU stage
`/data2/FreeToken/runs/dev_T05/r045_section14_v14_cpu_20261008_030500/report.json`
is mode `0444`, SHA-256
`4f1924d48c56c8f5235996ca2419384bc93b88cfb44be7b7c0188ad921b0784f`.
It records `72 passed`, CPU guard, empty CVD, and no service, GPU, or lock
action. Its read-only source manifest is SHA-256
`e9c0c8e8f77591bb4503622e82afae13533948259198da49c93932f56ca55499`.

## v14 finding

**PASS for the targeted v13 defects.**

- `analyze_d02_timeline` now requires three pairs containing six distinct
  UIDs. Each repetition receives one unused D02 timeline key
  `(step, t, rids, bs)` and retains that selected tuple in the result. The new
  regression rejects both UID reuse and a shared multi-UID timeline step.
- `run_t05_h1_diagnostic` now returns only pending UID-pair data. Its arm
  wrapper runs the existing owned-service stop first, then computes the SC5
  binding and final raw D02 SHA-256 values. The regression makes the stop
  callback append a final D02 row and proves the returned SHA and row count
  include it.
- A cleanup exception still escapes the existing stop path. The post-stop
  analyzer is not reached and no false-ready SC5 result is written.

The v13 SC3 byte-window/`k=0` behavior and expanded FILEdry writer coverage
were unchanged and are outside this narrow review.

## Decision

The targeted v14 tooling changes pass review. This remains CPU-only tooling
evidence: future `E2-R040e` measurement is not closed, so no formal FILEdry,
startup signature, GPU service, or launch is approved.
