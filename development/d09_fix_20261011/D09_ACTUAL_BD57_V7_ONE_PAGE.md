# D09 actual bd57 v7 replay

Candidate `7d8d389ee5d85de7e4f8e533f35c27f4c4c02690` ran on the dedicated remote worktree with CUDA hidden. The sealed batch164 exact-input SHA and all four raw-round pins passed. The replay used real Scheduler, CacheManager, Req bookkeeping, LinearStatePool, and FLA metadata; only model forward was replaced by a deterministic CPU state write plus `Req.complete_one`.

Enabled D09 admitted the target at **20,282**, created the exact entry, and matched conv/recurrent/PLE state at P against a separate cold reference. Default-off admitted at **20,160**, created no exact entry, and took no boundary snapshot. Thus the run demonstrates the requested v7 source-path change without a GPU, service, or API call.

The exact stdout/stderr digests and source/input pins are in `D09_ACTUAL_BD57_V7_EXECUTION_RECEIPT.json` (SHA `7cb05ee15ced764ce86b5d2005091536d2c1c5c987e933a1012616d7dfbfbd9e`). Independent review remains required; this is CPU evidence only.
