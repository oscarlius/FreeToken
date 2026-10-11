# R067d retry1 actual terminal independent review

Written at `2026-10-09T17:47:51.6071933Z`. Scope: sealed retry1 raw run only. This review did not start a GPU process, HTTP call, service, or build, and did not modify raw artifacts.

## Verdict

`not_met`.

The sealed raw record contains a valid `P=8192, T=1` cold A/B product comparison. Cold A and B are identical, but the first generated token differs from hot: hot `39`, cold `248046` at token index `0`. That is the frozen product stop condition, so this is neither `failed_harness` nor `blocked`.

## Integrity and bindings

- `RAW_MANIFEST.sha256`: `e2e3cf442b0a467a241b10d530920a12cc95893dd371255420f9af7e15bc7fb6`; all 123 listed raw files were independently rehashed with no mismatch, missing path, or unlisted regular file.
- `terminal.json`: `666e60498c6b1ae400242befe5d2974565bb34716a828e1433df61e99f6ac636`; batch 143, terminal verdict `not_met`, 4 services and 8 generation calls.
- Freeze config, CPU review, and root admission all match their binding hashes: `88a587...a8d92`, `2f5082...b773a8`, and `42dd9...003ba9` respectively.

## Direct runtime evidence

All six hot requests (`seed`, `t1`, `t64` at each of 8192 and 8256) are `valid`. Cold A and B both use the same 8192+1 input hash `9f1baff...62969e9`, produce the same response hash `4993d...425cc3`, resolve `hybrid_radix`, and report actual cache tokens `0`.

The cold evidence binds the frozen geometry `donor [0,P+1), rewind P, ordinary [P,P+T)`, records donor children at 0/4096/8192 with outer cache 0, and marks the successful single request as the ordinary tail-and-rewind proof. Hot observations show the 8192 checkpoint restore trajectory and actual cache tokens 8192.

The early terminal stop follows the authorized configured rule. It did not need to exhaust the unused service/call allowance. D12 was not triggered. The owned cleanup readback hash is `4475e38c6fcecd5f8f5f1e98f27279bf12a1b8c8aa99c075a9892d1bf270c191`; it records four owned births, four service attempts, and eight calls. The coordination log later records D09 start only after this raw seal and cleanup, with the same two hashes.

## Limits

This review validates the sealed retry1 round, not a new target-model run, a later remediation, or D12 acceptance. D09 was active during review, so current global GPU emptiness was deliberately not treated as a condition for this round-owned cleanup readback.
