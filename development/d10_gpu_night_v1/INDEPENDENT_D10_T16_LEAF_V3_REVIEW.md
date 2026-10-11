# Independent D10 T16 leaf v3 review

**Review time:** 2026-10-10T02:39+08:00  
**Leaf verdict:** **PASS — startup and source binding only**

The canonical public file dry-run receipt is regular, non-symlink, and `0444` at `/data2/FreeToken/runs/dev_T16/reviews/E2-D10-T16-night-20261010_file_dry_run_v3.json`. Its SHA256 is `b5892df160a98e3f735108baa6f6f6873a995ae609b322f14eb6b01e16a39a6b`.

The receipt is `ft_t16_real_path_dry_run/v1`, binds D10/RID `E2-D10-T16-night-20261010`, candidate `22ff3a389eae3724cdca9a45f2e19577082a2032`, parent `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`, and the exact nine-hash v7 source map. Importing the live `d10_owned_launch_v7.py` and calling `source_hashes('D10')` returned the same nine entries.

The dry run passed without allocating a batch or GPU lock, starting a service, sending requests, or creating a formal round. It enumerated the eight frozen arms. The real protocol count is 100 requests: four layer-major arms use one cold case and four non-layer-major arms use two cold cases, with the frozen ready/cold/tax derivation. This leaf review approves only default-off startup readiness and source binding. It states no GPU execution, performance result, terminal round, or product acceptance.

The consumer requires exactly the fields in the adjacent startup JSON: schema, RID/card, candidate/parent, `verdict: PASS`, `approved: true`, exact source map, and exact v3 dry-run SHA. After upload it must be read back through `require_leaf_review('D10')` before use.
