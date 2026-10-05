# D16 equivalence readers

This package implements the CPU schedule compiler and decision readers from
`PLAN_20261005_重新规划.md` section 4.1. Run from this worktree with
`PYTHONPATH=scripts python -m equiv_suite <command>`.

```text
compile --d0 <warm-d0.jsonl> --donor-uid <uid> --hit-uid <uid> \
  --cached-tokens <actual-hit> --prompt-tokens <actual-prompt> --output <schedule.json>
check-structure --d0 <reference-d0.jsonl> --uid <uid> --schedule <schedule.json>
evaluate --evidence <verified-evidence.json> --output <decision.json>
replay --t16-fixture <retained-t16_failed_full_tail.json> \
  --t16-runner <retained-t16_full_tail_base_runner.py> \
  --r023-review <review_batch51.json> --r023-review-sha256 <sha256> --output <replay.json>
```

The compiler copies the actual D0 `start,end,mode,subchunks` fields. It retains
the donor's extra computed row and the one-token checkpoint rewind; it does
not trim a 3585-row donor into a 3584-row donor. Missing structural fields,
multi-request records, gaps and contradictory old request metadata stop
compilation. The generated JSON filepath is the `FT_DEV_PREFILL_SCHEDULE` value.

Structure verification precedes comparison. Two independent reference process
identities, identical actual prompt-ID hashes, identical reference outputs,
four byte-equal restore roles, absolute continuation coordinates, initial
state and empty fresh-state indices are required. Matching measurements still
require independent review. An ordinary-cold envelope never changes the
decision. A warm/reference mismatch remains `not_met`; a missing operator
diagnostic is reported explicitly.

Historical replay invokes the pinned retained T16 validator. R019 and R021
have thirteen events and rows on both sides. Their failed rounds stay failed;
the replay checks the old false tail-count claim. R023 has four passing restore
roles and no same-structure cold reference, so its new-gate result is
`indeterminate`. Its historical `not_met` verdict remains intact.

These commands neither acquire a GPU nor launch a service. Live S-continuation,
S-batch, S-parking, S-cache and S-interleave runners and the delivered T17 batch
script remain pending. The CPU readers alone do not close D16 or T17.

`path_readers.py` provides CPU-only readers for two-slot and four-slot batch,
parking, cache, and interleave captures. Batch records require distinct process
and run-event identities plus one unique per-slot event identity and a lower-case
64-hex prompt-ID hash. If batch and singles first fork for a slot, that slot
must retain the D03 `logits_probe.py` comparison structure in
`top2_logit_difference[uid]`: an adapter maps `fork_generation_index`, the
original prompt SHA and prompt token IDs, the shared generated prefix (whose
length equals the fork), and the actual captured context IDs. The reader
recomputes the D03 `input_prefix_sha256`, input length, `k=1`, and final input
`positions` row. The preserved D03 `peer_vs_recompute` metrics must have
`first_top1_mismatch=0`, `top1_per_position=[false]`,
`top2_margin`, and `reference_top2_margin`. D03 does not retain top-1 token
IDs, so this is a context-and-margin diagnostic only; it does not establish
the identities of the generated fork tokens. The adapter also binds both slot
event identities, both complete process identities, and raw
`capture_receipt_base64` to a lower-case 64-hex `capture_receipt_sha256`.
An original-artifact reader must verify those receipt bytes before constructing
this evidence; an opaque SHA string is not byte proof. This in-memory adapter
does not establish that caller-supplied bytes came from a retained artifact.
Missing or unaligned D03
diagnostics make the reader `indeterminate`. Batch-vs-single output differences remain a non-admitting envelope. Parking requires all four byte-equal restore roles
before equal output can matter. Cache requires distinct cold and warmed
process/event/cache-state bindings plus a captured path, generation, and
hit/miss observation; its output has `cache_accepted=false`. Interleave
requires the same two slots to record exactly one `prefill`/`long_prefill`
event and one `decode`/`decode` event on distinct slot UIDs, with matching prompt-ID hashes in stable
repeat order and independent batch/repeat/singles process and event identities.
Missing or malformed capture bindings are `indeterminate`; every
path-reader output keeps `admitted=false`.

`continuation.run_case(resources, case)` now sequences the retained resource
runner: a health-only donor/hit process, the D0-compiled read-only schedule,
two fresh health-only references, and optionally an ordinary-cold output
comparison. It reads physical sampled IDs, state files and PID/start ticks;
each reference's actual D0 segments must match the compiled schedule. State
failure, reference instability and warm/reference inequality stop the case.
The exact first-subchunk absolute end comes from the warm D0 record.

This library does not reserve a batch or own the GPU lock. The delivered outer
wrapper, operator-difference producer, full batch/parking/cache/interleave
execution and numerical state envelope are still pending. Local fake-service
tests prove orchestration only; every result keeps `admitted=false`.
