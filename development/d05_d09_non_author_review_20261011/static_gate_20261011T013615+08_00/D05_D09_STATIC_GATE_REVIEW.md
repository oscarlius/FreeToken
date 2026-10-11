## Code Review Summary

**Files Reviewed:** 8
**Total Issues:** 3

### By Severity

- CRITICAL: 0
- HIGH: 2
- MEDIUM: 1
- LOW: 0

### Issues

[HIGH] Required D05 v6 real-Scheduler replay is absent
File: tests/scheduler/test_hybrid_cache_manager.py:229
Issue: The test uses a mocked orward_batch and manually changes request length. The candidate receipt says the corrected lifecycle fixture has not been rerun, so it does not prove enabled reuse at P=13504.
Fix: Bind a fresh real Scheduler v6 replay and CPU-hidden result to the frozen candidate.

[HIGH] Required D09 v7 enabled/off comparison is absent
File: tests/scheduler/test_hybrid_cache_manager.py:162
Issue: The new 20160→20282 case constructs CacheManager/Req directly. The Scheduler seam is also mocked and is not the sealed raw v7 replay, so it cannot prove enabled=20282 and off=20160.
Fix: Bind a fresh real Scheduler v7 replay with the exact sealed input and both mode assertions.

[MEDIUM] D05 activation variable is documented incorrectly
File: README.md:87
Issue: It documents FT_D05_ALIGNED_DECODE_STATE, but nv.py:50 uses FREETOKEN_ as the prefix. The documented setting has no effect.
Fix: Document FREETOKEN_D05_ALIGNED_DECODE_STATE=1 and test the documented configuration name.

### Recommendation

REQUEST CHANGES — static ownership/default analysis is favorable, but mandatory real-v6/v7 evidence and the D05 configuration-documentation repair are required. This review is CPU/static scope only.
