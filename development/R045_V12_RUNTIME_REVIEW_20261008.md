# R045 v12 runtime review — 2026-10-08

## Scope and evidence

This is an independent read-only review of
`development/r045_section14_draft_v12/source/`, its `READINESS.md`,
`cpu_report.json`, and the sealed Linux CPU report
`/data2/FreeToken/runs/dev_R045/r045_section14_v12_cpu_20261008_023838/report.json`.
The report SHA-256 is
`74e1ab12034bc02e83f8dfd7d15af294663176df7ae2cd13c4f246cb327965e2` and
records 67 CPU-guarded tests with no service, request, GPU, or GPU-lock side
effect. It is CPU evidence only. `E2-R040e` is still unmeasured, so formal
FILEdry, startup review, and any launch remain unavailable.

## Verified corrections

- `run_stall_ordinary` now treats the first token callback as a marker only.
  The prefill is dispatched from a separate bounded thread; both decode and
  interference threads are joined and their failures propagate. The callback
  no longer blocks the decode SSE reader.
- The performance service-file writer rejects D0, pause, and route-trace
  environment settings. SC2 continues to label physical Detoken sidecar time
  separately from the monotonic SSE transport clock.
- The actual `effb996` D02 producer is
  `python/freetoken/moe/d0_decode.py:D0DecodeRecorder`. It writes each decode
  timeline row with `step`, `t`, `bs`, `rids`, and ordered per-layer
  `copy_start_ms`, `copy_end_ms`, `compute_start_ms`, and `compute_end_ms`.
  It refuses incomplete layer/event sets before appending the row. The v12
  `analyze_d02_timeline` reads the three raw D02 files, checks the two actual
  request UIDs occur in a common decode step, checks every layer field, and
  records SHA-256 values for all three artifacts. The ordinary observer
  sidecar is emitted separately as `sc5_timeline`; it is not presented as a
  layer timing source.
- The H1 diagnostic invokes the D02 `two-decode` probe with two different
  prompts (`--same-prompt 0`), obtains its actual two UIDs from the probe
  output, then separately validates each of the three H1 repetitions through
  the original D06 validator. This avoids requiring two H1 UIDs.

## Findings requiring a v13 repair


### P0 — SC5 binds only the first of three diagnostic two-decode repetitions

`run_t05_h1_diagnostic` requests `two-decode --reps 3`, but extracts UIDs only
from `two_raw["reps"][0]["per_way"]` and calls `analyze_d02_timeline` once for
that first pair. It never establishes that the other two different-prompt
repetitions each had their own two-UID decode step, complete per-layer fields,
or artifact interval. The actual D02 producer schema supports the required
fields, but v12's evidence is one-repetition evidence rather than the complete
three-repetition diagnostic claim.

Minimal repair: retain all three two-decode repetition UID pairs, bind each to
its own D02 timeline interval/step and SHA-covered output, and reject missing
or partial per-repetition coverage. Do not use the ordinary observer's input or
token timestamps as substitute layer timings.
### P0 — SC3 does not produce a per-repetition `k/3` measurement

`sc3_prefill_evidence` parses every `#new-seq` line in the entire arm's
`serve.log`, then sets `k_same_batch_new_seq_2` to the count across that whole
file. It records pair-side UID/input hashes, but does not record a
before/after log position, timestamp interval, or an exclusion result for each
of the three `c_pair_short` repetitions. Other cold, two-decode, and stall
requests in the same service log can therefore contribute to `k`.

The code correctly says that `serve.log` itself contains no UID and does not
claim a direct UID binding. That makes the missing same-window proof material:
the current value is neither a pair-specific `k/3` nor evidence that a zero
was observed for all three pair repetitions. The CPU test for zero only uses a
log with no matching line; it does not exercise an interleaved foreign request.

Minimal repair: capture a stable before/after byte offset (or line interval)
around each pair request, retain that repetition's two physical
input/sidecar/API records, and prove no foreign request was active in the same
window. Classify each of the three repetitions as `merged`, `not_merged`, or
`not_captured`; calculate `k` from only `merged` intervals. `k=0` remains a
valid result only when all three intervals were captured and classified
`not_merged`; an uncaptured interval is an evidence gap, not zero.

### P1 — FILEdry omits one real H1 diagnostic output

`run_t05_h1_diagnostic` writes `timeline_two_decode.json` before reading its
UIDs. `dry_h1_diagnostic` probes the D02 JSONLs and `d_h1.json`, but not this
actual `timeline_two_decode.json` writer output. Consequently the same-path
FILEdry does not cover all diagnostic output paths used by the formal runtime.
Add that probe (and assert it is the same path passed to `--out`) before the
next review.

## Decision

v12 improves the D02 producer binding, SC5 field validation, H1 repetition
validation, and callback behavior. It is **not tooling-ready** because SC3
cannot establish the required per-repetition `k/3` evidence, and FILEdry is
incomplete for the two-decode output. This is not a formal launch approval.

