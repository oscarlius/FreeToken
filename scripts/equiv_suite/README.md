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

`retained_d03.py` is a read-only CPU reader for one exact D03 logits index row
per arm, with separate UID/sequence selections rather than polling for a latest
row. It loads only a caller-pinned SHA-verified D03 `logits_probe.py`, then
reuses its binding, tensor loading, metrics, and state difference. Every
logits/state role needs a matching SHA and regular in-arm file, while the
original index bytes and selected raw JSONL line are returned as Base64 plus
SHA. Original D03 index rows stay unchanged: each arm instead needs a separately
SHA-pinned `ft_equiv_retained_service/v1` sidecar. The sidecar binds the actual
index SHA, selected raw-line SHA, UID/sequence, process identity, and event
identity. Missing or mismatched sidecars are `indeterminate`; caller metadata
alone never supplies a service identity.

`retained_state.py` reads two exact legacy `donate` snapshots without changing
their indexes. A SHA-pinned `ft_equiv_retained_state_sidecar/v1` binds the whole
index and selected raw line, original int32-le prompt IDs and snapshot prefix,
four full role-file hashes, independent process and event identities. Missing,
malformed, nonfinite, or unaligned evidence is `indeterminate`. Floating-point
roles report bitwise equality, max-absolute error and RMS; integer roles report
exact equality. These offline snapshot metrics always keep `admitted=false`
and cannot establish restore equivalence, model acceptance, or a T17 gate.

`sampler_capture.py` is an explicit, instance-level diagnostic observer.  A
caller creates `QueryRegistry`, binds each target UID to its original prompt
token IDs and event identity, and then calls `SamplerCapture(...,
max_captures=..., max_bytes=...).attach(engine)`.  Before that one Engine's
`forward_batch` it freezes CPU `input_ids[:device_len]`; its wrapped sampler
calls the original sampler exactly once and returns that original result.  Only
after successful sampling does it atomically publish a fp32 CPU logits snapshot
and JSON receipt in a unique `capture-######` child directory, then atomically
extends the root manifest. The explicit limits are cumulative across retained
serialized snapshot and receipt bytes and across all captured rows. The receipt records pre-complete context IDs and hashes,
generation index, native logits shape/dtype, sampled token ID, process identity,
and event identity.  A single scheduled request is retained but has
`sbatch_coverage=false`; it never proves S-batch coverage.  Invalid bindings,
duplicate UID/generation/event tuples, nonfinite logits, or either explicit
budget limit leave no partial valid capture and are `indeterminate` errors.
The caller must invoke `finalize(expected)` with the exact expected
UID/generation/event set.  Only a `complete` terminal manifest is readable;
any missing capture or observer error seals it as `failed` and rejects every
capture beneath that root.

`read_logits_receipt()` requires a capture ID and caller-pinned receipt SHA. It
verifies every manifest entry, retained receipt/snapshot byte count and SHA, and
all row/context/process/event/native-shape bindings before loading only a
caller-SHA-pinned D03 `logits_probe.py` to calculate self-logits metrics.
It does not claim a D03 capture binding, engine support, model equivalence, or
performance result; all of its output remains `admitted=false`.

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
