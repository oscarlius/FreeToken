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
