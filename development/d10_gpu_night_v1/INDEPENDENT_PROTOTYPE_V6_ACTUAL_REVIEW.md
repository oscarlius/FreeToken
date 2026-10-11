# Independent D10 Prototype V6 Actual Review

**Verdict: FAIL.** This review is CPU-only and did not start a GPU, HTTP endpoint,
service, or compilation.

`LINUX_CPU_RECEIPT_V6.json` is a sealed regular remote file (`0444`), SHA-256
`5a0bb3543e5badd020b952e4e7d74cc44fb9facb701dcba9ee87fe029cfa4b98`.
Its source and genuine R045 fixture hashes match the current corresponding files,
and its three contract tests pass. That receipt does not prove the required runtime
admission or performance threshold semantics.

The parser reads real nested AIPerf records. It correctly rejects the retained
wave1/wave2 records for the original gate because their per-request speeds are
22.03–22.53 tokens/s, below 30. More seriously, `fixed_gate()` does not check speed:
a fresh raw-record repro with two exact 256-token outputs at 1.0 tokens/s passed.

V6 also leaves its runtime provenance incomplete. The parent binds neither D07 nor
the dynamically imported runner V6 nor the two input files; both inputs are remote
mode `0664`. A sealed minimal admission with an arbitrary D09 object and truthy T16
object, but no native provenance or D09 terminal/manifest hashes, was accepted.
The child reserves the API port only, does not consume D07's child/birth receipt, and
checks GPU idle only during cleanup.

The current child body did pass useful CPU mocks: the success path emitted
`measured_pending_independent_review` with reservations `[2,4,6,8]`; missing
two-request branch proof emitted `not_met`; a dispatch exception emitted
`failed_harness` and partial `[2,4]`. These behaviors cannot make the candidate
admissible until the stated provenance, port, and fixed-speed gates are repaired and
re-evidenced.
