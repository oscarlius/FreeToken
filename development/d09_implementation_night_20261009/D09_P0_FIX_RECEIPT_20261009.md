# D09 P0 Fix Receipt

- Recorded: 2026-10-09T22:56:00+08:00
- Scope: freetoken/development/e2d09-message-boundary-v1
- Source HEAD: bdbfcf0d8c0a20f5c983dd78c23092f2aa04021d
- Remote worktree: /data2/FreeToken/wt/d09-message-boundary-v1 at the same HEAD.

## Independent-review P0 remediation

1. A MessageBoundaryCarrier is created at admission and shared by overlap-created continuations. Snapshot metadata now remains visible when the preceding chunk drains after the continuation already exists.
2. A non-page-aligned D09 boundary uses a singleton exact cache entry. It owns the complete physical page through ceil(boundary/page_size) but exposes only the literal token length, preserving the matching GDN state. It participates in locks, eviction, integrity accounting, and rebuild reset.
3. The D09 boundary cut takes priority over hybrid page alignment, so 20282 and 22558 are not floored.

## CPU verification (no GPU, service, HTTP, compilation, or JIT)

    ssh 172.16.108.9 "source /data2/FreeToken/venv/bin/activate && cd /data2/FreeToken/wt/d09-message-boundary-v1 && PYTHONPATH=python pytest -q tests/scheduler/test_hybrid_cache_manager.py tests/scheduler/test_prefill_anchor_cut_switch.py tests/scheduler/test_switch_defaults.py"
    28 passed in 3.82s

The package includes page-size-64 tests for both sealed literal boundaries, full physical-page ownership, exact token-length matching, GDN state restoration, integrity accounting, and a continuation admitted before drain.

GPU remains untested and is required for the planned T16/T17 runtime acceptance only.
