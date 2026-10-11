# ROOT night-tail launch review material

This is a self-review input only.  It is not an approval and it must not be
used to create a measured result.  Source is frozen at remote stage
`/data2/FreeToken/runs/dev_night_tail_queue_20261009/source/runtime_v2/`.

## Launches after independent review

| Round | Root command | FILEdry receipt |
|---|---|---|
| R047 night | `/data2/FreeToken/venv/bin/python .../runtime_v2/r047/night_r047_executor.py --run --review-receipt <sealed-review.json> --worktree /data2/FreeToken/wt/e2base1-ordinary-rewind --out /data2/_shared/runs/ft_rounds` | `2cce87336ce3d8e7862f95b6d5b2e967664ad5e8f98479a144bcfa712bd3bc07` |
| R052a night | `/data2/FreeToken/venv/bin/python .../runtime_v2/r052a/r052_t11_followup_prepare.py --run` | `90deb05b05f331dd5455c58643a7e71554b604a5307a73f6352311844ec6fbfb` |
| R044 night | `/data2/FreeToken/venv/bin/python .../runtime_v2/r044/r044_prepare_v6.py --run --worktree /data2/FreeToken/wt/e2base1-ordinary-rewind --output-root /data2/_shared/runs/ft_rounds` | `cb5f187028cb3652377e8d6a36a5c6fb50306df36076f798ff140e766fe5d938` |

Use the literal runtime_v2 prefix in each command.  The R047 executor is
`runtime_v2/r047/night_r047_executor.py`; it imports the task-owned clone and
therefore its owned child does not re-enter a frozen v12 gate.

## Required sealed review contracts

| Round | Required path | Contract |
|---|---|---|
| R047 night | `/data2/FreeToken/runs/dev_T03b/reviews/E2-R047-v12/{review,pin}.json` | `ft_t03b_r047_review/v3`, `ft_t03b_r047_review_pin/v1`; requires night RID, executor SHA, clone prepare SHA, input/source bindings and canonical output root. |
| R052a night | `/data2/FreeToken/runs/dev_R052/reviews/E2-R052a-night-20261009_startup_review_v8.json` | `ft_r052_startup_review/v7`; requires clone source hashes, night FILEdry receipt SHA, candidate/parent `0aa`, and authorized prerequisite object. |
| R044 night | `/data2/FreeToken/runs/dev_T10/reviews/E2-R044-v7/{review,pin}.json` | `ft_t10_startup_review/v3`, `ft_t10_startup_review_pin/v1`; requires night RID, clone source hashes, night FILEdry SHA, canonical output root. |

R047/R044 review directory labels are inherited constants from the clone but
their embedded RID and source hashes must be the night values.  Reviewers must
reject a receipt whose RID or clone hash differs.

## Source identities

Operational entry SHA-256: R047 `bc0a321d404999539bc2031a1408712394041e7fba11eb708b0606b647e4b3ea`; R052a `2dba0bedeb1bf206635358c1c40aed88c8042d9f828f3a9d7fedd33a0a50e2c7`; R044 `13e31fe41470c70642f0bc0c0ca8aee5c3c3ec39c6c34ef4475e43d4c52660de`.

Shared authorization JSON SHA-256: `86bb5d56f70993cb3ce628e643ebcfa68f909bae901e17697852afbda036ebe7`; helper SHA-256: `1416ffcb5cfea776825ce75b6a650a214a823be5160937df62c032a0ecb81d27`.
Each clone's complete source tree is covered by the FILEdry receipt's
`source_sha256`/`source_copies`; review must recompute it from runtime_v2,
excluding only test and `__pycache__` files.

## Evidence and policy boundary

Technical gates retained: clean `0aa23431…` worktree; R041/T20/R052/R040f
closures; R047 six-arm input/metric path; R052 actual UID=8 trace plus exactly
one continuation; R044 sealed E2-R017 traces and 24 UID sampler evidence.

Policy exception evidence: R040g round.json is `failed_harness` (SHA
`e5685d…`); R045's real AIPerf first attempt terminal is `failed_harness`, its
retry terminal is `exports_pending_review`, and neither is a D04 `not_met`.
The binding used here is the separate sealed pre-reservation artifact
`/data2/FreeToken/runs/dev_T05/reviews/R045_V18_PRE_RESERVATION_BLOCK_20261009.json`,
SHA `3738f8ed…`: it says full gate blocked before reservation because R040g is
failed_harness.  It is not a measurement result.

The independent queue authorization records only these facts.  A terminal
`not_met` stops its one item and permits the next authorized item; it never
converts a factual failed/blocked state into `measured`.
