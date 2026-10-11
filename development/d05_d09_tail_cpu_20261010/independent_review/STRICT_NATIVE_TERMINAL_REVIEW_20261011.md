# D05 strict-native non-author review

Written at: 2026-10-11T00:12:07.7065323+08:00

**Status: REQUEST_CHANGES.** The current strict-native artifact cannot establish either required number and Q1–Q5 remain **UNREPRODUCED**.

| Gate | Result |
|---|---|
| Real bd57 Scheduler._forward route | Missing |
| Frozen batch164 raw prompt/config/splits + SHA binding | Missing |
| Raw-track transition sequence binding | Missing |
| One bd57 source/predicate for 13,376 and 20,160 | Missing |
| Native bookkeeping chosen by Scheduler, rather than script-driven state | Missing |

strict_native_lengths.py does not import, construct, or call Scheduler._forward. It manufactures D05/D09 donors with 	orch.arange, including the 20,160 case. It then sets device_len=1 and drives Req.complete_one() in a loop. This does exercise a local cache object, but it does not bind the state transitions to the frozen D09 batch164 request or to a Scheduler decision/predicate.

No parser or SHA verification for the frozen batch164 raw prompt/configuration/splits appears in the artifact, nor does it record exercised hashes for bd57 Scheduler, Req, CacheManager, and the raw track sequence. A number emitted by the current script therefore cannot answer Q1–Q5 or support an attribution.

The machine-readable evidence is [STRICT_NATIVE_TERMINAL_REVIEW_20261011.json](STRICT_NATIVE_TERMINAL_REVIEW_20261011.json).

## Required terminal evidence

A final candidate must run an actual bd57 Scheduler._forward route and preserve native Req.complete_one/cache bookkeeping. It must SHA-bind the frozen batch164 carrier, prompt/configuration/splits, and raw track sequence, then record both 13,376 and 20,160 under the same source and predicate before any Q1–Q5 interpretation.
