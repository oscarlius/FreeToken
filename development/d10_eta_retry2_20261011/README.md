# D10 eta retry2 CPU package

This task-owned package supersedes neither `d10_eta_20261010` nor any release source. It is default-inert: GPU work requires `--run-gpu`, a linked 481 worktree, frozen X, and mode-0444 SHA-bound admission/review receipts.

Retry2 removes the unsupported `--moe-collect-stats` append. It does not enable D0 or route tracing. During Engine graph capture only, it retains the final complete 48-layer `ensure_experts` input tensors; GraphRunner captures batch sizes in descending order, making that final sweep the bs=1 graph. Every retained buffer must have bs=1 shape and a distinct allocation, preventing an overwritten shared scratch tensor from standing in for a layer route. After a fixed-bs1, untimed graph warmup, each retained graph-produced slot id is reversed through `id_of_slot` and must resolve through `slot_for_id[layer, expert]` to the identical live slot. The receipt binds each retained buffer's pointer and shape plus its resolved routed expert ids and slots. Stable map snapshots remain supplementary evidence.

T_copy invokes the real `fast_index_copy_multi_jit` 48 times per sample: 7 or 8 rows from each real layer's pinned host-bank pointer descriptor, totaling 367 rows. Targets must be physically free and disjoint from the proved graph-routed slots; mapping tensors are snapshot-checked before/after every timing block.

CPU admission must parse the exact final engine argv through the materialized 481 parser. It must never treat a hybrid parser check as proof for eta.
