# Closed-loop X/Y runner independent review

**Status: APPROVED_CODE_READY_CONDITIONAL_ON_READONLY_ADMISSION_BINDING.** Written `2026-10-10T22:57:22.363548+08:00`. No measurement was run by this review.

Pinned runner `ca29a5acfaa11f55ae2f9c6b890d829d0de258eaf5bf7ab13e827b348689a577`, tests `3b05e5dd5224b1f306c686f2ffda0e097a364a8476d3e4d8e3cdad6a0b578044`, and INPUT_FREEZE `e8cba66e674f3b4997c59e142322e0b6382cf99749c34518062d42c1dcffc930`. Fresh CPU test evidence: **3 passed in 0.20s**, including the real R045 raw AIPerf fixture and sibling metrics join.

The runner executes X and Y once each with two requests at concurrency two, for four calls total. It keeps raw exports and joins raw/metrics through two unique request IDs; per-lane TPS is `1000 / inter_token_latency_ms`. It validates X length completions and the 7.8 TPS anomaly floor, snapshots the service PID/start-ticks before and after each group, and normalizes TimeoutExpired byte output before writing receipts.

D0 records only appended stock `bs=2` rows and explicitly labels `missing/(steps*2*480)` as a deduplicated shared-batch average, not a UID m.

Before execution, the read-only admission must bind this exact runner/input set **and** INPUT_FREEZE/preregistration P1/P2 hash and deadline. The runner validates its own source and inputs but does not independently hash INPUT_FREEZE or adjudicate P1/P2.
