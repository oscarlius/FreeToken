# E2-R067c-d20-short-tail-retry1 CPU packet

This is a separate, non-admitted retry-1 packet. It preserves the original
10-service/14-call inputs, schedules, product criteria, and artifact hashes.
It does not modify the failed original round.

The original `hot_p8192` seed was one logical 8193-token request logged as two
prefill fragments: 512 and 7681 tokens. Each row correctly reported one new
sequence. Retry1 changes only that controller predicate: every row must report
one sequence, their new-token counts must sum to the expected request length,
and every row must retain the expected cache count. It additionally requires
the actual API prompt token count to equal the exact input length and exactly
one scoped exact-ID HTTP response in the captured serve window. Existing
`request_evidence` remains responsible for UID, exact-ID, API usage, and
observation association.

`retry1_cpu_validate.py` accepts only `--filedry --out <new-directory>`.
`--run` is rejected. It creates no service, GPU lock, HTTP generation, batch,
admission, or signature.

The retry family ledger remains root-owned at
`/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl`.
Retry1 does not copy, reset, or hash-bind that mutable ledger. Root must create
the later `RETRY1_ROOT_STARTUP_ADMISSION.json` only after its fresh review and
gates.
