# Window01 D0 single: independent evidence addendum

Reviewed at: `2026-10-11T01:53:02.630420+08:00`. Local, read-only review.

- The 24/24 entries in `GPU_D0_SINGLE_EVIDENCE_MANIFEST.json` match; manifest SHA-256: `1f129001f083608ca09b48147631997814d1afdc35c8a56f45b29d3d055068e8`.
- The unique AIPerf request is `56954309-af55-4ced-8823-f4d71c074e01`: one call, frozen X lane 0, 1,179 prompt tokens, 256 completion tokens, `finish_reason=length`. The service was `offload`, with only `FT_DEV_D0` and its output path in the diagnostic environment.
- Recomputing the request-bound D0 ledger yields `42932 / (255 × 48 × 10) = 0.3507516340`. Steps are the contiguous range 0–254, every row has `bs=1`, `rids=[0]`, 48 layers, and matching row/sub-layer totals.
- Compared with the frozen X shared-batch reference `0.3824264706`, the absolute difference is `3.167483660` percentage points, below the specified 5pp guard. This is a content-dominant consistency guard only; it is neither a speed nor causality conclusion.
- Cleanup is recorded as proved with no remaining members or errors and no retained lock.

## Limitation

`d0_decode.json` aggregates 257 calls per layer and reports a different miss rate. The selected, request-bound 255-row step ledger is the applicable metric here. A later use of the generic aggregate needs an explicit explanation of the extra calls.

**Verdict:** `SUPPORTED_D0_SINGLE_METERING_WITH_LIMITATIONS`. This does not establish η, D08/D10 performance, GPU acceptance, or production activation.
