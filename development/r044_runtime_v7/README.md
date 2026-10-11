# r044_runtime_v7

This CPU-only successor consumes `E2-R040f` only as `failed_harness` and requires a measured `E2-R040g` closure whose `base.commit` and `experimental.candidate_commit` are both `effb9969706922ddad9e59b96377e46469ebe97f`. Historical T20 evidence remains explicitly bound to `0aa23431e5b800797543bdecbf35a01045131d7d`.

The review directory is uniquely `runs/dev_T10/reviews/E2-R044-v7`. FILEdry and startup-review schemas remain `/v3`: their structural consumer contracts are unchanged, while the unique path and source-hash binding prevent v6 artifact reuse. Formal FILEdry and GPU execution remain pending.
