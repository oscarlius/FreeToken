# S2 retry-1 actual terminal independent review

**Verdict: VALID_MEASUREMENT_SUBSET_ONLY.** This permits S3's independent-review precondition. It is not S2 product acceptance, a quality result, an `ignore_eos` acceptance result, or a two-lane result.

The actual S2 engine append slice `[63383,67383)` hashes to `efeaa60a...` and contains `draft layer loaded`; historic S1 slice `[51855,59385)` is negative. S2 ran explicitly with `parallel: 1`, same v0.1.41 binary as S1, plus `--mtp`, `--spec 4`, and `--spec-min-p 0.5`.

All seven probe artifacts are valid: cold32K 4/4 and short2K 3/3 have `cached_tokens=0`, the expected prompt/completion lengths, and `finish_reason=length`. Mean decode rate is 77.17 tok/s for cold32K and 79.06 tok/s for short2K. Original128 AIPerf has two raw HTTP 200 records, no errors or cancellation, and 64.62 output tok/s; the fixed-256 group also has two HTTP 200 records but has two OSL mismatches and output mean 54, so it remains unsupported non-acceptance evidence.

Against same-binary S1, cold and short decode means are respectively +22.95% and +24.02%; Original128 AIPerf output rate is +33.46%. S1 differs in `spec=2` and has no MTP, while S2 also changes spec/min-p, so these are combined-configuration differences and cannot be assigned to MTP alone.

The original terminal’s `cleanup_ok=false` and bare `AssertionError()` are preserved. Root recovery later proved owner/service and groups absent, no GPU compute, empty TCP state, 8085 reuse bind, and exact owner-lock release without extra service or generation. It does not prove which original predicate failed. S3 should add a new diagnostic-only pre-unlock snapshot wrapper; do not alter or rerun S2.
