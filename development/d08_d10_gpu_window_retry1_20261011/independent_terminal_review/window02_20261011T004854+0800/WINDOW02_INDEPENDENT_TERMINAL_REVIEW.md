# Window02 independent terminal review

**Verdict:** `FAILED_HARNESS_PENDING_OWNED_RECOVERY_REVIEW`.

The only completed reference request is the pre-stop offload single lane: one raw and one metric record, HTTP 200, not cancelled, 1179 prompt tokens, exactly 256 `length` completion tokens, 33.1444148745098 ms inter-token latency, and **30.1709957405 decode TPS**. Its executed input SHA is `8181287a…423c`; it is byte-identical to line 0 of frozen X SHA `f63b3623…1162`.

η is `failed_harness`: its engine log rejects `--moe-collect-stats` before model loading or measurement; it has no numerical η result. Hybrid is also `failed_harness`: its readiness deadline expired while PLE/expert load was underway. It created one new service and no generation-call or runtime-config/measurement artifact. The original cleanup carrier is false due to `OSError(98)`; no closure claim is made until separately reviewed root-owned recovery evidence binds exact identity and cleanup state.

No D0 trace/source-pin inference, parsed cache/fetch conclusion, or D08 H1/H0 conclusion is supported by this run.
