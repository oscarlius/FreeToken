# D05/D09 tail CPU preregistration review

Reviewed at `2026-10-11T00:00:15.992425+08:00`. **REQUEST CHANGES before any same-source interpretation.**

The frozen stop rule is sound: both 13,376 and 20,160 must arise from byte-pinned bd57 product code and the same exercised rejection condition; exact D09 raw flags, prompts, splits, and hashes must bind the D09 lane.

## Blocking finding

`actual_bd57_r052_replay.py:94-98` assigns `target.cached_len` and `target.device_len` inside the fake engine forward. That manufactures a cache/scheduler result, while the preregistration permits a double only for token-model side effects. The existing D05 fixture receipt therefore cannot prove same-source under this new freeze. A compliant remote replay must leave cache length and rejection decisions to real bd57 product methods; otherwise it must remain `UNREPRODUCED`.

`actual_bd57_r052_replay.py:76-84` also bypasses `Scheduler.__init__` through `object.__new__`, so configuration predicates are not covered. It is a secondary gap unless the final method constructs the real pinned Scheduler or explicitly limits its claim to a `_forward` seam.

No D09 causal attribution, same-source conclusion, or product proposal is approved at this stage.
