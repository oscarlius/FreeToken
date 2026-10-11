# D10 staggered overlap CPU preparation design

This is a design and command-plan artifact, not an implemented CUDA prototype and not a performance result.

The candidate is 481d3a7. The existing graph contract captures a complete `model.forward()` in `GraphRunner._capture_graphs` (`engine/graph.py:147-204`), so a staggered implementation cannot safely overlap two requests by merely launching two existing graphs. The relevant expert path is `layers/moe.py:323-326` (`ensure_experts` then `copy_missing`) and `moe/offload_cache.py:293` (`prefill_copy_stream`) with event ordering around lines 946-1013. These are the hooks to instrument after formal admission.

The bounded design is: retain per-request state and expert-miss plans; expose a per-layer transfer-ready event; enqueue request A's miss copy while request B executes its compute segment; fence each layer's compute on its own ready event; record transfer, compute, wait, and bubble intervals. Cache slots must remain request-owned or have explicit release events. The shared prefill double-buffer path must not be reused for decode without proving slot ownership and event ordering.

CPU preparation stops at command generation and input validation. It does not emulate GPU overlap, invent timeline data, start a service, acquire a lock, or invoke CUDA. Runtime stop criteria are: missing T05/D02 per-layer trace, unresolved cache/state isolation, either lane <=30 tok/s, or T16 failure. Formal implementation remains default-off and requires an independent worktree plus admission.
