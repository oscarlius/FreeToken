# R040g tail-entry independent local review — 2026-10-08

## Verdict

**NOT APPROVED for a readiness claim.** The three current runtime entrypoints correctly express the new `E2-R040g` `measured` gate, validate both `base.commit` and `experimental.candidate_commit` against `effb9969706922ddad9e59b96377e46469ebe97f`, preserve `E2-R040f` as `failed_harness`, and retain historical `0aa23431…` as metadata.  Their inherited regression suites, however, are not updated to the new gate/version contracts and fail locally.  The reported “14 regressions pass” cannot support the complete entry/consumer regression claim.

## Entry-chain findings

| Package | Entry / admission | Child argv | file-dry / review consumer | Finding |
| --- | --- | --- | --- | --- |
| `r045_section14_draft_v17` | `source/r045_d06_t05_prepare.py:500-507` consumes `E2-R040f` as `failed_harness`, then `E2-R040g` as `measured`; `:491-498` validates both R040g commit fields as effb. | `:438-439` runs this same v17 entry as owned child. | `:451-484` fixes the v17 hidden sibling and requires `ft_r045_dry_run/v17`; `:483-489` consumes the v17 review before the predecessor gates. | Chain is internally connected.  Old tests still expect v16 paths/version strings and old mocks omit a valid R040g closure. |
| `r044_runtime_v7` | `r044_prepare_v6.py:78-94` validates R040g and consumes R040f as `failed_harness`; it also retains T20/R052/R052a gates. | `:305` emits self-bound owned-child argv. | `:48-61` creates `.dryrun_R044_*`; `:109-140` consumes readonly receipt and review; `:309-326` consumes review/queue before reserve or lock. | Chain is internally connected.  Current file-dry schema/review schema remain `/v3` despite the v7 review directory; this needs an explicit policy decision if “new schema” was required. |
| `r047_runtime_v12` | `r047_prepare_v11.py:51-52,143-162` requires R040f `failed_harness`, R040g `measured`, validates both effb fields, and stores historical 0aa separately. | `:556-559` binds emitted child to executor/review/worktree/output root. | `:469-512` consumes canonical readonly FD and sealed review; `:563-585`, `:691-705` call predecessor/review validation before launch/lock. | Chain is internally connected.  Its FD/review schemas remain `/v3` while the review path is `E2-R047-v12`; same policy clarification applies. |

No path or RID crossover was found in these active entry-to-child links: R045 remains `E2-R045`, R044 remains `E2-R044`, R047 remains `E2-R047`.  All three retain their science configuration in the reviewed entry code (R045/R047 explicitly retain 98304 and 0.88 settings; R044 binds the retained T10 capture/replay sources).

## Local evidence

1. `python -m pytest -q freetoken/development/r047_runtime_v12/tests/test_r040g_predecessor_v12.py` → **11 passed**. This new targeted set verifies the three source files reject wrong R040g base/candidate commits; it also verifies R044/R047 R040f `failed_harness` consumption and R045 later-gate reachability.
2. `python -m pytest -q freetoken/development/r044_runtime_v7/tests/test_t10_e2_r044_prepare.py freetoken/development/r047_runtime_v12/tests/test_r040g_predecessor_v12.py freetoken/development/r047_runtime_v12/tests/test_r047_prepare_v10.py` → **70 passed, 9 failed, 1 skipped**. Failures are old fixture paths/mocks that return no R040g document before the new validator can proceed.  `r044_runtime_v7/tests/test_t10_e2_r044_prepare.py:14` also still expects R040f `measured`.
3. `python -m pytest -q freetoken/development/r045_section14_draft_v17/source/tests/test_r045_d06_t05_prepare.py freetoken/development/r045_section14_draft_v17/source/tests/test_r045_v16_closed_pin_actual.py` → **36 passed, 13 failed, 12 skipped**. The failures prove stale v16 assertions remain: `test_r045_d06_t05_prepare.py:243,437,452` expect v16 path/review strings, and `test_r045_v16_closed_pin_actual.py:20` expects `HARNESS_VERSION == r045-section14-v16`. Other old mocks supply `{}` for the newly mandatory R040g closure, masking later lifecycle behavior.

## Required correction before approval

Update or retire the inherited v16/v6/v11 regression expectations and fixtures so that they create a valid R040g closure with both commit fields equal to effb, expect R040f `failed_harness`, and assert each new FD/review schema/path policy. Then rerun the complete local closure. This review made no source changes and did not run remote CPU, FD, GPU, ports, or services.
