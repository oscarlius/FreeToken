Release e3 restore package RELEASE-E3-20261012-02 (op-hak, GLM-window restore; identity copy of release_e3, diff in development/ophak_glm_nvfp4_p0_20261012/release_e3_02_vs_release_e3.diff).
Approval RELEASE-E3-20261012-02 re-runs release/e3 (commit 9db0ee776c25) with --prefill-anchor-cut-min-tokens 32768 after the GLM NVFP4 single-card test window.
Window approval (conditional pre-sign by freetoken-06): plan/OPHAK_GLM_WINDOW_APPROVAL_20261012.md, sha256 b7b0d27afdf26e652d0644e181a977bcff76c3ece7cbb07d087f5ed4bad495f0. Conditions C1-C8 are checked by op-hak before W1.
Frozen ops: runs/dev_release/release_e3_ops_v1_20261012 (unchanged from release_e3).
Failure path (deploy_conditional.recover_after_restore_failure): stop with this package, then run restore14/deploy_conditional.py --execute (release-e2). ROLLBACK184 is never started from this package.
first_cold_baseline: the release_e3 reference (021e2ab3...), reused; no new Q1 in the window.
EXECUTION_TIME_PREFLIGHT.json is written by start_approved_release.py at execution time and is not part of this copy.
