# D05/D09 tail CPU replay preregistration

Created: 2026-10-10 23:57 Asia/Shanghai
Scope: CPU-only evidence review. No GPU, service, production action, or source modification outside this directory.

## Frozen inputs

- D05 replay method: `development/d05_same_source_cpu_20261010/test_actual_bd57_r052_replay.py`.
- D09 raw round: `/data2/_shared/runs/ft_rounds/E2-D09-T17-reapply-bd57-20261010`, expected round SHA `a6655b59`.
- Product code under review is the real bd57 LinearStatePool, CacheManager, and Scheduler path. Only token-model side effects may be replaced by the existing replay fixture method.

## Same-source definition and stop rule

"Same source" requires identical exercised product code bytes and the identical rejection predicate/condition. A test double may replace token-model side effects only; it must not replace, patch, or return cache lengths, rejection decisions, or scheduler outcomes.

Before interpreting any question, the replay must obtain both 13,376 (D05) and 20,160 (D09) from the real path. Any other result, exception, missing pinned raw carrier, or source/predicate mismatch is `UNREPRODUCED`; analysis stops without attribution.

## Questions

1. Does carrier 20,282 reach `cache_req_hybrid`?
2. Does the exact D09 commit enter it; what is its result, actual failed condition, and code lines?
3. What is the origin of 20,160 versus alignment at 20,224?
4. Is D05/D09 "same" under the definition above?
5. Proposal only, default-off CPU tests for conventional/recurrent/PLE plus T16 requirements and person-days; no implementation fix.