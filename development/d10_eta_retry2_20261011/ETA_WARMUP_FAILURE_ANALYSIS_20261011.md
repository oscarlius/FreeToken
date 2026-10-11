# η retry2 warmup failure analysis

Written at: 2026-10-11 local wall clock. This is a read-only post-failure analysis; it does not alter the sealed η source or create a retry.

The reported terminal condition was `warm_until_stable_cache` exhausting its 32 raw bs=1 `graph.replay()` attempts after graph capture had completed. Therefore no timing sample, η, copy/compute overlap result, or D10 performance conclusion exists.

The strongest source-supported hypothesis is recurrent-state drift, not a fixed-token guarantee failure. `GraphCaptureBuffer` carries a persistent `table_idx`; `GraphRunner._capture_graphs` documents that the captured graph's GatedDeltaNet gather/scatter uses that stable address, and it fills the graph buffer with the dummy request's live linear-state slot. `set_fixed_bs1_graph_input` replaces that same `table_idx` with the live dummy slot, then `warm_until_stable_cache` calls raw `graph.replay()` repeatedly. These calls execute the captured linear-state gather/scatter each time. A fixed token does not make the recurrent hidden state fixed, so subsequent router outputs can differ and the LRU `slot_for_id`/`id_of_slot` mappings can keep changing.

The observed condition proves only that those two maps were not equal over the bounded loop. It does not prove which layer missed, whether a specific route was invalid, or a graph/cache defect. `ensure_experts` can mutate mappings on misses/evictions; the current receipt did not survive the stable-map gate to emit the later per-layer route proof. The raw replay also bypasses `GraphRunner.replay(batch)`, including `buffer.copy_from(batch)` and `attn_backend.prepare_for_replay(batch)`; that is a second confounder, though the benchmark intentionally sets the graph buffer once before replay.

A future design would need a separately approved, non-timed method to reset or snapshot/restore the GDN state around warmup, and to prove its relation to the timed graph. That is outside the sealed retry2 source and is not proposed as a retry here.
