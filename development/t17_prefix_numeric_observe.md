# T17 first-GDN numerical observer

This test-only observer copies first-GDN inputs only for the absolute shared interval
`[512, 8192)`. It records `conv_in`, `q`, `k`, `v`, `g`, and `beta` separately for
each real prefill child, with the request UID and absolute child coordinates.

The observer does not alter the request, state pool, tracking flags, or `return_h`.
It CPU-clones `conv_in` and the kernel inputs before the original kernel call; it only
copies `h` from that original call's return tuple.
It accepts an `h` snapshot only when the original tracked kernel returned its tuple.
The target `h` row is computed from the requested absolute boundary,
`prepare_chunk_offsets(cu_seqlens, 64)`, and the kernel's documented 64-token
boundary contract. The receipt separately retains the actual FLA tracked row and
absolute endpoint. Missing tuple, incomplete interval, duplicate boundary state, or
an out-of-range target row is invalid evidence.

For any `cached=4608` child spanning the target, `8192` is row `56`:
`(8192 - 4608) / 64`. The observer captures that exact returned row. A cold
`device=8257` child may have its normal tracking endpoint at `8256` (row `57`),
which is recorded as metadata but does not move the target capture to row `57`.
Receipts include source hashes and the observed first-GDN
projection quant-method class (or `null` when unavailable), without inferring a
scheme from checkpoint names. They also record the selected kernel name/class and
requested backend for `in_proj_qkvz` and `in_proj_ba`.

`install(model, pool, output_dir=..., boundary=8192)` returns an observer. The
launcher must call `has_uid(uid)` and then `finalize(uid)` after the matching request
completes. The CPU copies are diagnostic overhead and do not establish T17 admission.
