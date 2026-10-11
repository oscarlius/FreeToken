Restore12: identity-only copy of Restore10 for the op-hak task A window (OPHAK_TASK_A_ANCHOR_CUT_20261011.md H3).
Same twelve reviewed restore sources with identity substitutions only (-10 -> -12 approval/rollback/run_dir).
observation_until unchanged (2026-10-12T09:00:00+08:00). df77cb baseline comparison and stop-before-rollback logic unchanged.
ROOT_FINAL_REVIEW.json binds the op-hak task A directive (independent_review_sha256 = b8232e31efca99be88addc44f55d30bea76f243d411e9b9b6cb03c02363599f4).
Restore12 cannot run before the main session writes "任务 A 放行" in the coordination log.
