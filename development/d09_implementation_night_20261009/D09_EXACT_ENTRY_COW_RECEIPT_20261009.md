# D09 Exact-Entry COW Receipt

- Recorded: 2026-10-09T23:03:09+08:00
- Source HEAD: c17b69a46cd512fbf3d127d3879bce92caae457b
- Remote worktree: /data2/FreeToken/wt/d09-message-boundary-v1 at the same HEAD.

## Second-review P0 repair

A hit at literal boundary 20282 or 22558 now reserves a private complete final page before its tail forward. CacheManager copies the donor physical KV slots through the configured KV pool, including QSA per-slot metadata. The request table is rewritten to that private page, so tail writes cannot change the singleton exact entry or a concurrent hit lane.

The exact-entry replacement transfers ownership of already shared full pages and frees the prior partial donor page, which was COWed at admission. Repeated replacement is covered by CPU tests.

## CPU verification

    PYTHONPATH=python pytest -q tests/scheduler/test_hybrid_cache_manager.py tests/scheduler/test_prefill_anchor_cut_switch.py tests/scheduler/test_switch_defaults.py tests/scheduler/test_anchor_cut_scheduler_wiring.py tests/scheduler/test_cache_rebuild.py
    39 passed in 4.25s

The complete independent-review command also reports 43 passed and the three existing base481 epoch-tuple assertion failures; those failures are unchanged and deliberately not modified.

No GPU, HTTP, service, JIT, NVCC, or compilation was run. GPU acceptance remains separate.
