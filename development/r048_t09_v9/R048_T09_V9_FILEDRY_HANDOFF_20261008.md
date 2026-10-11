# E2-R048 / T09 v9 formal FILEdry handoff

The same-user (`dell`), same-entry formal FILEdry passed from
`/data2/FreeToken`. The authoritative output directory is the frozen source's
default `DRY_RUN`, `/data2/_shared/runs/ft_rounds/.dryrun_E2-R048_98304_v9`.

The read-only receipt is
`dry_run_receipt.json`, SHA-256
`fff4dcac2d4d678ff5440267587a65be5f0564c793c87a23db4b88ae5da7ebd9`.
After it was made read-only, the frozen v9 source's unparameterized
`require_file_dry_run()` accepted it from that default location. The receipt records all five arms, both
performance and diagnostic writer paths, the exact queue exception, and false
values for service start, requests, GPU lock, batch allocation, and formal RID
creation.

At both admission and post-receipt verification, `/data2/_shared/runs/ft_rounds/E2-R049b`
was absent. `/data2/_shared/runs/ft_rounds/E2-R048` and the GPU lock were also
absent. An independent R reviewer must create a new v9 startup review before
any controller invocation; this handoff grants no GPU authorization.
