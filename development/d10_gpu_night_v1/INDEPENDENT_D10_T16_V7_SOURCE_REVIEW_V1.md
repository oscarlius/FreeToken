# Independent D10 T16 v7 source review

Written at `2026-10-09T18:21:55.4433478Z`. This is a read-only CPU source and filedry-evidence review. It did not start a public dry-run, GPU process, service, HTTP request, or compiler, and did not inspect D09's current lock or runtime.

## Verdict

`PASS_WITH_CANONICAL_RECEIPT_NAMING_GAP`.

The remote v7 launcher is the requested immutable source (`b27197...101e95`, mode `0444`). Its v6→v7 change is limited to v3 review/receipt/scope references, a 100-call scope correction, and a real source-inspected CPU mock. The common adapter v3, pinned base runner, and frozen helper hashes are unchanged from v6.

## CPU filedry evidence

The named local receipt has SHA256 `f3ae380...905182`. The remote actual evidence at `evidence_cpu_filedry_v7/terminal.json` has the same SHA256 and mode `0444`, so their bytes are identical.

The remote CPU filedry contains eight actual arm records, not a single constant: four layer-major records at 12 calls and four non-layer-major records at 13 calls. Its total is `48 + 52 = 100`; all eight listener rebind proofs and the terminal's `all_listener_rebound` are true. It records no GPU, service, HTTP, lock, or formal-round side effect.

The remote named path `LINUX_CPU_FILEDRY_RECEIPT_V7_T16.json` is currently absent. That prevents treating the named receipt as canonical public-dry-run input even though the remote terminal is byte-equivalent evidence.

## Next gate

After S3 cleanup, root must run the real public `--dry-run --card D10` to create canonical v3 evidence. A separate review can then decide whether `startup_review_v3.json` is consumable as `ft_t16_leaf_startup_review/v1`.
