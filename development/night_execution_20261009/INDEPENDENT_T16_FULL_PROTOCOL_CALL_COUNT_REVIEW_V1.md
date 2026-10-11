# Independent T16 full-protocol call-count review

Written at `2026-10-09T18:16:51.5882739Z`; this was a read-only CPU source review. It did not start or query a GPU process, HTTP service, compiler, or current D09 state.

## Verdict

The fixed D09/T16 full protocol contains **100 generation HTTP calls**, not 96. This corrects metadata only. It does not change the protocol or authorize another run.

The retry1 adapter (`ed628f...776e3`) pins the base runner (`22ed68...a2f1d1`) to `t16_frozen_helpers_v1`. The frozen `cold_eq.py` (`1fe951...5a6093`) makes one POST per selected case. Although it imports `build_text` from frozen `probe_ft_cold32k.py` (`68e6c3...cc306d`), it never calls that helper's `main`, so the helper adds zero calls to each `cold_eq` case.

The frozen checkpoint tax helper (`a67471...8a0c0`) sets `REPS=5`; each repetition calls one single-message and one multi-message request. That is ten calls per arm. The runner also sends one `say ok` readiness generation request per arm.

| Arm type | Arms | Per-arm calls | Total |
| --- | ---: | ---: | ---: |
| Layer-major | 4 | 1 readiness + 1 cold case + 10 tax = 12 | 48 |
| Non-layer-major | 4 | 1 readiness + 2 cold cases + 10 tax = 13 | 52 |
| Full fixed protocol | 8 | — | **100** |

The former 96 count assumed every arm had one cold case. It omitted `short` and `chunked` being two distinct cold cases on each of the four non-layer-major arms.

## Records requiring a root addendum

The three identical CPU-filedry records at `d09_t16_night_v1` carry `calls=96` with SHA256 `3188acf...c931bd`. The 20261009 and retry1 D09 user-scope approvals carry `planned_generation_calls=96` with SHA256 `dbcba0...60b54` and `22f4b8...8f9746`. The immutable retry1 owned-launch source (`c7ffe7...87810f`) embeds the same 96-call expectation and mock.

Root should append a correction binding this review and set the protocol total to 100 while leaving those existing bytes and the fixed source protocol untouched. No new GPU retry is consumed, and no currently running D09 process is within this review's scope.
