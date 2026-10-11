# D09 bd57 native binding repair — CPU-ready handoff

The old controller required c17 while the declared candidate was bd57, and the old runner rejected the already approved bd57-to-c17 native links. The repaired packet binds `bd57cfdccc2a935d46cb0a89b8b36be7a18706de` at `/data2/FreeToken/wt/d09-page-conservation-20261010`.

`release-e2` must hold regular, exact-pinned modules. The bd57 tree must hold symlinks only for the two named modules; each must resolve to the exact regular module in clean `c17b69a46cd512fbf3d127d3879bce92caae457b`, with the same CPython-310 filename, SHA-256 and size. No copied binary, alternate link target, build or ABI change is accepted.

Remote CPU evidence passed: the two binding tests passed with CUDA hidden, and the real-path file-writer dry run produced [the v2 receipt](/data2/FreeToken/runs/dev_T16/reviews/E2-D09-T16-reapply-bd57-20261010_file_dry_run_v2.json), SHA-256 `114ae0deefc5183092277f5c8ea785e4d2daf6209d0dc9287fe01928067ce5b9`. The dry run explicitly injected only a temporary lock path and a `0 MiB` idle answer into the immutable base helper. It retained the actual git, process, import and file-writer checks, and recorded zero services, requests, GPU locks, batches and formal rounds.

The existing native-provenance decision is unchanged and sealed read-only (`0444`). Earlier CPU receipts and manifests are preserved but source-bound to the old executable hashes, so they are superseded for admission. A new independent review must seal the v2 startup review; this packet does not admit a controller, GPU, service, HTTP call, formal T16 verdict or T17.
