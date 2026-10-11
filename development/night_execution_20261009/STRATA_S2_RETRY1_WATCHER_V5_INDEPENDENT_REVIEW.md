# Independent watcher review — D09 T16 to Strata S2 retry-1 v5

Remote review clock: `2026-10-10T01:03:23.916963+08:00`. Source SHA: `194ab227e367065594ea1fd47eacccd1caa9cd840d5a61daa30a84df48ecdfc2`.

## Verdict

**WATCHER_V5_STARTUP_APPROVED_CONDITIONAL.** Root may start v5 after its final source/readback check. This approves only the gated watcher, never S2 measurement or product acceptance.

V5 closes W8: it requires the S2 runner, R2 FILEdry receipt, and independent review to be regular non-symlink files before use. It closes W9: new immutable artifacts receive content fsync, mode `0444`, post-chmod fsync, and parent-directory fsync; driver log and coordination append are also durable.

Local and remote AST parsing passed. A remote temporary-directory CPU test passed: regular evidence was accepted, a symlink was rejected, and sealed output was mode `0444` after the fsync path completed. Local and remote source SHA match.

V4 `246860:165931524` was stopped before v5 was created. No v5 watcher is running. D09 child `199552:165838035` is absent and its exact status is terminal `failed`; this is not treated as PASS. No cleanup, port-preflight, root admission, or S2 driver artifact exists. V5 must still prove resource cleanup before creating any of them.

No GPU, service, HTTP request, compilation, or model mutation was performed.
