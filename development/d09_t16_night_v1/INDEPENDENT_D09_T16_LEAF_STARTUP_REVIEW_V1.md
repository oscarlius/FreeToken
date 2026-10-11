# Independent D09 T16 Leaf Startup Review V1

**Verdict: PASS — canonical startup-admission dry-run only.**

The sealed canonical receipt is a real file at
`/data2/FreeToken/runs/dev_T16/reviews/E2-D09-T16-night-20261010-retry1_file_dry_run_v1.json`,
mode `0444`, SHA-256 `2dc02cd09f6fb0d1482a0d97d34a721d9fce460da39433bde17fee586dba9571`.
It reports the retry-1 RID, candidate `c17b69a46cd512fbf3d127d3879bce92caae457b`, parent
`481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`, eight arms, and `passed: true`.

Fresh remote validation imported the actual launcher and successfully ran its
`require_file_dry_run("D09")` gate. The receipt's nine source hashes equal the
current launcher-derived source hashes; each source is a non-symlink, non-writable
regular file. The JSON companion has the exact fields consumed by
`require_leaf_review("D09")`: schema, RID/card/commit binding, `PASS`,
`approved: true`, the full source-hash map, and the receipt hash.

The result covers only canonical public dry-run startup admission. The receipt
explicitly records no GPU lock, service, requests, batch allocation, or formal round.
