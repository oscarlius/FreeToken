# R067c retry2 CPU packet

This is the final, CPU-only preparation packet for `E2-R067c-d20-short-tail-retry2`.
It preserves the frozen R067c input, criteria, ten service arms, fourteen calls,
and retry1 multi-fragment prefill geometry repair.  It corrects retry1's
`argv_sha256` fields after the run-ID/path retargeting using the exact D07 JSON
encoding (`sha256(json.dumps(argv, separators=(",", ":")).encode())`).

`prepare_retry2_packet.py` materializes immutable configuration and runner
sources. `retry2_cpu_validate.py --filedry` verifies only local packet shape,
hashes, paths, and CPU semantics. It never starts a service or uses a GPU.
`--run` is deliberately prohibited. The rendered child repeats service argv,
arm path, and scoped-environment checks before its GPU-lock call.

The mutable family retry ledger is root-owned at
`/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl`.
It is deliberately neither copied nor hash-bound here. Any admission, GPU run,
or restoration remains root-owned and requires separate review.
