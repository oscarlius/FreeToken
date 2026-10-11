# Night tail queue CPU preparation

This task-owned directory prepares the already approved queue in this exact
order: `R067d -> R047 -> Strata -> R052a -> R044`.  It does not alter any
existing round, product source, formal output, GPU lock, server, or endpoint.

## Current entry map

| Item | Current source | Candidate / baseline | Formal runtime budget | Required closures |
|---|---|---|---|---|
| R047 / T03b | `../r047_runtime_v12/r047_prepare_v11.py` | `0aa23431...` E2-base.1; 98K / 0.88 | 6 service arms; each does 3 positive streamed turns and one negative request | R041 kept; R040/R040f failed_harness; R040g/R046g/R045/R044 measured |
| R052a / T11 | `../r052_runtime_v8/r052_t11_followup_prepare.py` | `0aa23431...` E2-base.1 | 1 target replay followed by exactly 1 continuation request | R041 kept; T20 failed_harness; R045 measured; R052 failed_harness |
| R044 / T10 | `../r044_runtime_v7/r044_prepare_v6.py` | `0aa23431...` E2-base.1; 98K / 0.88 | 2 modes x 3 services x 24 requests, each capped at 200 tokens: 144 requests / 28,800 maximum tokens | T20/R052/R040f failed_harness; R052a/R040g measured |

These entries deliberately retain their original E2-base.1 baseline.  The
current `481d3a7` candidate must be recorded separately when needed; it cannot
silently replace a baseline embedded in old round identity, inputs, hashes or
formal closures.

## R047 FILEdry

`r047_filedry_prepare.py` uses the existing R047 v12 emitter and executor.  It
does not reimplement D04/lifecycle/gate behavior.  On Linux, after prerequisites
and the reviewed receipt exist, it emits a task-owned executor then invokes only
the existing executor's `--file-dry-run` branch.  That branch copies sources and
writes six service plans but must leave service, HTTP, GPU lock, batch allocation
and the formal RID directory untouched.

The maximum retry policy is external to this helper: one FILEdry plus at most
one correction retry per item.  A `not_met` result terminates only that item's
formal attempt; it does not authorize another service attempt or alter later
items' prerequisites.

## Authorized independent terminal queue (v2)

`night_tail_queue_authorization.json` binds the user-authorized scheduling
exception to real, immutable evidence: `E2-R040g` is `failed_harness`, and the
latest real R045 AIPerf terminal is also `failed_harness`.  It does not call
either outcome `measured` and does not create or change any formal round.

The task-owned `r047_authorized_v13.py`, `r052a_authorized_v9.py`, and
`r044_authorized_v8.py` alter only the FILEdry admission metadata.  They retain
the frozen sources' candidate, retained inputs, source hashes, service arm
counts, request/token budgets, and real metric consumers.  A terminal
`not_met` for R047 authorizes R052a; a terminal `not_met` for R052a authorizes
R044.  This is an independent queue rule, not a claimed measurement result.

Linux CPU evidence is sealed at
`/data2/FreeToken/runs/dev_night_tail_queue_20261009/linux_cpu_authorized_v2_evidence.json`
with SHA-256 `f5511ebd5aacf758c069fdea8f5ad6bebb1dbd1b6abf95c337e089a296da2703`.
It records all existing suites and the three successful no-live-effect FILEdry
receipts.  Root and independent review still decide whether any resulting
candidate is eligible for a later reviewed `--run` action.
