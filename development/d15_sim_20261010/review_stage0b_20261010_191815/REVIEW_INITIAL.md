# D15 Stage 0b lag1 CPU independent review — initial evidence

Timestamp: 2026-10-10 19:18–19:25 CST

Candidate inspected remotely: `/data2/FreeToken/wt/e2d15-adapt-lag1`, branch
`exp/e2d15-adapt-lag1`, `HEAD=825655305d69df94d3d2f79c3f416234bfe890e6`.
The worktree was clean at both status checks.  This is not a GPU acceptance
record.

## Scope and state

`988c9e1..8256553` changes four files: `README.md`, `docs/d15_expert_cache.md`,
`python/freetoken/moe/offload_cache.py`, and
`tests/moe/test_expert_profile.py`.  The code change is the volatile-owner
repair at `offload_cache.py:1041-1055`; the test addition is lines 281-362 of
`test_expert_profile.py`.  No uncommitted KIMI change, `lag1` implementation,
or new lag1 test was present when inspected.

## Review findings

### HIGH — stage 0b lag1 contract is absent

`python/freetoken/moe/offload_cache.py:997-1080` performs all bank copies,
mapping publication, and completion synchronously inside
`apply_profile_adaptation`.  It creates no auxiliary-copy stream/event and has
no pending transaction published at a later scheduler step.  The current
boundary drains all relevant streams before calling it
(`python/freetoken/moe/adaptation_boundary.py:59-76`).  Therefore it cannot
demonstrate “copy on an auxiliary stream, do not publish before its completion,
and publish at least one step later.”

Impact: the requested lag1 safety/property is not implemented, so T21 must not
start on this candidate.

Minimal repair: represent a pending adaptation separately from live mappings;
enqueue bank copies and record a dedicated completion event; leave
`slot_for_id`/`id_of_slot` untouched in the producing step; at the next
scheduler boundary, publish only after that event is observed complete.  If it
is incomplete, retain the old map and block a second pending transaction.  A
rollback must wait for the helper stream and restore both data and maps, then
lock the opt-in policy if restore fails.

### HIGH — required D0 per-swap receipt does not exist

`python/freetoken/moe/offload_cache.py:469-760` has generic D0 decode and
prefill instrumentation.  `_d0_write_decode` only emits aggregate policy stats
at lines 543-550.  No code records a receipt containing actual step, layer,
expert, slot, bytes, copy-start, copy-complete, and publish time for an
adaptation swap.

Impact: a CPU enqueue wall-clock value could be mistaken for completed GPU
work, contrary to the D15 plan, and there is no artifact to audit transaction
ordering.

Minimal repair: record a receipt per planned swap.  Keep enqueue time explicitly
separate from CUDA-event completion; populate copy-complete only after the
dedicated copy-complete event is observed/synchronized, and record publish time
only after map publication.  Include the actual step/layer/expert/slot and
bytes from the executed transaction.

### MEDIUM — existing CPU tests do not exercise the lag1 safety surface

`tests/moe/test_adaptation_boundary.py:41-111` uses `FakeCache` and
`FakeCoordinator`; its ordering assertion checks strings appended by the fake.
`tests/moe/test_expert_profile.py:250-278` obtains a proof using CPU fake
events/streams, and the new tests at 281-362 cover synchronous map consistency
and rollback only.  No test covers decode top-k protection, multiple requests,
prefill volatile range `[0, 2E)`, an incomplete pending copy, or publication on
the next step.

Minimal repair: add deterministic CPU tests that use the real cache/pending
transaction state and a controllable event.  Assert that mappings and bank
contents stay unchanged while the event is incomplete; assert no protected
current-step top-k slot is selected; then complete the event and enter a later
boundary before asserting publication.  Cover batched/multi-request top-k,
prefill buffer occupancy, invalid map publication, and rollback after a
partially completed copy.  Do not use a fake call-order list as the sole proof.

### MEDIUM — full CPU MoE suite is currently red

With the candidate code forced into the FreeToken venv via `PYTHONPATH=python`,
`CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`,
`pytest -q tests/moe` produced `72 passed, 103 skipped, 3 failed`.  All failures
are in `tests/moe/test_offload.py` at lines 113, 199, and 373, where
`get_global_ctx()` raises `AssertionError: Global context is not set` from
`python/freetoken/core.py:239`.  These files are outside `988c9e1..8256553`,
so this is recorded as a validation blocker/gap rather than attributed to the
volatile-owner patch without a baseline comparison.

## Positive evidence and validation limits

- Default LRU CPU contract is included in the targeted suite
  (`test_expert_profile.py:115-136`) and passed.  It supports default-state
  compatibility only; it is not a CUDA/output-token equivalence result.
- Targeted CPU scope passed: `38 passed in 3.35s` for
  `test_expert_profile.py`, `test_adaptation_boundary.py`,
  `test_d0_fields.py`, and `test_d0_decode.py`.
- `git diff --check` was clean and `py_compile` succeeded for both reviewed
  source files and both relevant test files.
- `ruff` was unavailable in `/data2/FreeToken/venv` (`No module named ruff`).
- An initial targeted run without `PYTHONPATH=python` collected the installed
  production source at `/data2/FreeToken/src/FreeToken` and failed four imports;
  that invocation is invalid for this candidate and was corrected above.

## Hash manifest

See `HASHMANIFEST.sha256` in this directory.

## Recommendation

REQUEST CHANGES.  The candidate’s existing synchronous volatile-slot repair is
well-tested on CPU, but it does not contain the requested lag1 implementation,
D0 receipts, or behavior-level regressions.  CPU evidence must not be promoted
to CUDA stream ordering or token-equivalence acceptance.
