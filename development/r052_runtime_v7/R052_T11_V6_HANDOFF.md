# E2-R052 / T11 v6 local delivery

This is a new local v6 closure. It leaves the root v5 entry and every prior
dry-run, review, and source snapshot unchanged. It does not authorize a
service, GPU lock, batch reservation, model port, request, FILEdry, startup
review, or `--run`.

## Fixed R045 exception

The only former `E2-R045 measured` dispatch prerequisite is now the fixed
HANDOFF section 8.7 exception:

```json
{"deferred_round":"E2-R045","reason":"R040f retry approval pending","no_data_dependency":true,"basis":"CODEX_HANDOFF_20261006.md §8.7"}
```

`queue_exception()` refuses both a directory and a symlink at the formal
`E2-R045` path. The same object is bound into the v6 dry receipt, startup
review, admission result, owned-launch receipt, and raw result. A changed
reason or omitted value fails validation.

## Preserved controls

Candidate `0aa23431e5b800797543bdecbf35a01045131d7d`, worktree, reverse-trace
SHA/index 7/history UID 8, token-cache classification, D0/anchor evidence,
private port pair, process ownership, and cleanup/lock behavior are unchanged.
R041 kept and the current T20 failed-harness checks remain mandatory.

The wrapper command is still constructed through `prepare_service_files`.
The v6 test executes the real `r052_d0_shutdown_startup_v1.main` with a fake
`freetoken.cli`: it accepts `['ft', 'serve', ...]` and rejects the historical
duplicated executable form.

## Required next gates

After the current GPU work is terminal and root explicitly releases this
stage: Linux CPU stage, exact default-path FILEdry, no-argument receipt
consumption, and an independent startup review are separate gates. R052 is a
first formal run; no result here claims it is ready or starts it.

## CPU and FILEdry evidence

The released CPU-only stage is
`/data2/FreeToken/runs/dev_R052/r052_v6_cpu_20261008T015417Z/source`.
With `/data2/FreeToken/venv/bin/python`, `CUDA_VISIBLE_DEVICES=''`, and
the existing R046 cpu_guard first in `PYTHONPATH`, its closure test run passed
42 tests. The frozen `source.SHA256` is
`438cc0d293b77c01a4d14adf8004607596bc3942a3e288ad4436a2d3013e6481`;
`cpu_stage_report.json` is
`afdc46f15612c76e27bd29fae481bceddf22e20ef8fbb754cde4a52e92e37a10`.

The canonical `/data2/FreeToken` FILEdry used that frozen source, created no
formal `E2-R052` directory, no service, request, lock, or batch, and produced
`/data2/_shared/runs/ft_rounds/.dryrun_R052_v6_E2-R052/dry_run_receipt.json`.
Its SHA256 is `b4cea2ca04d3495117b022a61809fb58e41cb1afecec8e52b01b81f1b761f02d`,
mode `0444`; the same source's no-argument `require_dry_run_receipt()` accepted
it. This is FILEdry evidence only and still does not authorize a startup review
or formal run.
