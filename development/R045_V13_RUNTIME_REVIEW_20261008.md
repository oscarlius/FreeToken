# R045 v13 runtime review — 2026-10-08

## Scope and CPU evidence

This independent read-only review examined the v13 source closure, its new
SC3/SC5/FILEdry paths, and Linux CPU stage
`/data2/FreeToken/runs/dev_T05/r045_section14_v13_cpu_20261008_030105`.
`report.json` hashes to
`ebbcc01dab06ff3305c396184c528f7bc77b351f26fed146dee794fd337b0ea3` and
records `70 passed, 1 warning`; the warning is the expected read-only pytest
cache warning. The source manifest is read-only and hashes to
`66da6e96f9561f9590297cb84aadca283e6b1ba9a30f52afa753983e91d5c0fa`.
The report records CPU guard, empty CVD, and no service, GPU, or lock action.

## v12 findings repaired

- **SC3 k/3:** `_run_pair_ordinary` captures each `c_pair_short` repetition's
  `serve.log` byte start/end around the real simultaneous two-request call.
  `sc3_prefill_evidence` requires exactly three two-record results, preserves
  their direct API/worker input UID and SHA bindings, parses only each bounded
  byte window, and emits `merged`, `not_merged`, or `not_captured`. It computes
  `k` only from `merged`; `k=0` is valid only for three captured windows. The
  regression places foreign `#new-seq:2` lines outside every captured interval
  and obtains zero, so other suite log entries do not affect k. The real
  adapter's worker-input validator requires the actual sidecar source
  `Scheduler._process_one_msg(UserMsg)`, matching the requested UserMsg proof.
- **SC5 D02:** the diagnostic invokes different-prompt `two-decode` with three
  repetitions, obtains all three actual UID pairs, and passes them to
  `analyze_d02_timeline`. That validator binds timeline rows to producer step
  rows by the exact `(step, t, rids, bs)` tuple, requires nonempty layers, and
  rejects non-finite or reversed copy/compute times. It SHA-binds the raw D02
  step, timeline, and prefill files. Its output is explicitly diagnostic and
  records `token_cap=512` with `exact_512_not_claimed`; ordinary-observer clock
  rows are separate and are not called layer timings.
- **FILEdry:** `dry_h1_diagnostic` now probes
  `timeline_two_decode.json` plus all six actual per-way token paths for the
  three repetitions, together with the D02 JSONLs and H1 output. The targeted
  test checks those writer paths.

## P1 — SC5 does not reject cross-repetition UID/step reuse

`analyze_d02_timeline` requires three two-UID pairs, but does not require all
six UIDs to be distinct. Repeated pairs can therefore each match the same
timeline row and be reported as three covered repetitions. Normal product UID
allocation should make that impossible, but this evidence validator must reject
it rather than rely on that expectation.

Minimal repair: require six distinct UIDs across the three pairs and retain a
unique matching D02 step per repetition; add a repeated-pair/step rejection
test. No new reader or runtime flow is needed.

## P0 — SC5 artifact SHA is computed before the diagnostic output is final

`run_t05_h1_diagnostic` calls `analyze_d02_timeline(directory/'d0', pairs)`
before it runs the H1 subprocess. H1 uses the same D02 environment and can
append prefill, decode-step, and decode-timeline rows. The returned artifact
SHA-256 values therefore bind the pre-H1 files, not the final diagnostic files
that the result claims to retain. Generate the SC5 artifact binding after H1
has completed and the owned service has stopped/flushed; retain the final
three-file SHA values in the result.

## Decision

The three v12 defects are materially repaired in the real writer and validator
paths. v13 remains CPU-only and is not formally ready: the P0 final-artifact
binding, the P1 reuse rejection, and the future `E2-R040e` measured prerequisite
remain before formal FILEdry, startup review, or launch.
