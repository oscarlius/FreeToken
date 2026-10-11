# r044_capture_path_retry1_20261010

This CPU-only successor consumes `E2-R040f` only as `failed_harness` and requires a measured `E2-R040g` closure whose `base.commit` and `experimental.candidate_commit` are both `effb9969706922ddad9e59b96377e46469ebe97f`. Historical T20 evidence remains explicitly bound to `0aa23431e5b800797543bdecbf35a01045131d7d`.

This retry is limited to the prior `failed_harness` capture-destination defect. Its RID is `E2-R044-night-20261010-retry1`; every service plan writes `FT_D16_SERVICE_CAPTURE_DIR` below `runs/dev_D16/E2-R044-night-20261010-retry1/<mode>/<arm>/capture`, and `capture_bindings` consumes that same path. Formal `ft_rounds` retains plans, logs, and raw-measurement artifacts only.

The review directory is uniquely `runs/dev_T10/reviews/E2-R044-night-20261010-retry1`. FILEdry and startup-review schemas remain `/v3`: their structural consumer contracts are unchanged, while the unique path and source-hash binding prevent prior artifact reuse. Formal FILEdry and GPU execution remain pending independent review.
