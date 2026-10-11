# R045 v15 targeted runtime review — 2026-10-08

## Scope and CPU evidence

This review considers only the v15 `normalized_serve` writer/validator repair.
The Linux CPU report at
`/data2/FreeToken/runs/dev_T05/r045_section14_v15_cpu_20261008_031500/report.json`
is mode `0444`, SHA-256
`aeff299960ce61cec32a9d69264eac26f70690281ca37e75720ed2b770a088fd`.
It records 73 passing tests, CPU guard, empty CVD, and no service, GPU, or lock
action. The read-only source manifest SHA-256 is
`ddba87906802594fda94bead433fdbd4fa07c7b9dd90f84ffdb40cfa48172d95`.

## Finding

**PASS for the targeted writer repair.**

`prepare_service_files` now writes the same protocol argv and port into both
`SERVE_CMD.txt` and `serve_argv.json`, while retaining the raw wrapper argv.
`normalized_serve` verifies both records agree, validates the fixed Python /
startup / observer-dir / `--` wrapper shape, validates the complete server
suffix against canonical `serve_argv(port)`, then compares only protocol argv
and port between P1 and P2. This permits their intentionally distinct observer
directories without ignoring wrapper drift.

The new writer-driven twin-positive test validates separately written P1/P2
records, then rejects a changed memory ratio, injected wrapper flag, and
foreign startup source. Existing `strict_log_args` still compares every parsed
`ServerArgs` key between arms, allowing only generated PID suffix differences;
it has not been weakened.

## Decision

The v15 normalized writer change passes targeted tool review. This is CPU-only
evidence. Future `E2-R040e` measurement and formal FILEdry remain outstanding;
this review does not approve a startup signature, GPU service, or launch.
