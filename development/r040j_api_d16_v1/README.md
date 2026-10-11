# R040j SDK D16 readiness retry

Terminal result (2026-10-09): batch124 is D04-closed `not_met`. The approved long-request batch/single pair had identical input, finish and usage but different full text. Five services were started and six calls completed before the required stop; no autonomous tooling retry follows this product criterion failure. See [the result](../../plan/01_测试与调研/results/T20-E2-R040j_20261009.md).

This is the first tooling retry of the authorized R040i API-only scope:
six services and eight SDK calls, same effb996 candidate, inputs, 98304/.88
configuration and full text/finish/usage comparison. Warm remains deferred.

R040i's 450-check loop had no sleep after successful non-ready HTTP health
responses and stopped its first service about 15 seconds after startup,
before any generation. The loading-response sequence is inferred from the
product's initialization semantics and timing; transient health bodies were
not saved in that failed round.
The sole runtime repair sleeps two seconds after every not-ready health
response, including HTTP 200 `loading`. The 450 checks and existing failure
cleanup remain unchanged. No native collector is introduced or repaired.

The CPU regression executes the actual `start()` function against a real
loopback HTTP server, covering loading-to-ready and exhausted loading.
Only model-process creation and timing are replaced at the test boundary.
CPU, actual FILEdry and an independent startup admission are required before
the new formal RID `E2-R040j-api-D16` can be launched.
