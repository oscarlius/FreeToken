# R055a D06 dry-run handoff

R055a is the approved letter-suffix retry for the pre-service R055 failures. Its formal RID is
`E2-R055a-gate-D06`; it does not create a new numeric R055 round. It remains queued behind
`E2-R050-gate-D15` and does not authorize a GPU launch.

## Server source package

The delivered immutable source set is `/data2/FreeToken/runs/dev_R055/r055a_real_path_source_v1/`.
Its MANIFEST SHA is `82ba087c25d5ed979cb96c883a3a960740eb9afcdd7a5d308d35b530153d727a`.
The formal launch and actual dry-run both use the same owner at this final path:

- `r055a_owned_launch.py`
- `r055a_gate_d06_prepare.py`
- `r055a_dryrun_base_v1.py`
- `r055_owned_launch.py`
- `r055_gate_d06_prepare.py`
- `d07_g3g4_prepare.py`
- `t16_private_port_base_runner.py`
- `t16_full_tail_base_runner.py`
- `t17_d14_runner.py`
- `t17_d14_observe.py`

The R055/R055 batch74/75 failed-harness directories and every formal R055 artifact are read-only
inputs and are not overwritten.

## Required server dry-run

Run as the intended FreeToken service user, from `/data2/FreeToken`, before requesting the new
startup review:

```bash
/data2/FreeToken/venv/bin/python runs/dev_R055/r055a_real_path_source_v1/r055a_owned_launch.py --dry-run
```

This invokes the same R055a adapter later used by `--run`; it does not start a service, acquire a
GPU lock, use 8095, send a model request, or create `ft_rounds/E2-R055a-gate-D06`. It creates the
single child `/data2/_shared/runs/ft_rounds/.dryrun_R055a_E2-R055a-gate-D06/`, checks the sealed
helper MD5/SHA and both worktrees, then performs all six actual arm file preparations plus PAUSE_ON:
environment and command files, observer copy/instrument/freeze, state-dump and output files, and
writability probes. It allocates a dynamic loopback port but does not start a process or create a
formal round directory.

The receipt is `dry_run_receipt.json`, is frozen to `0444`, and binds all source SHA256 values, user,
cwd, owner/adapter paths, six arm writes, PAUSE_ON writes, and false service/request/lock/batch/formal
flags. A new independent review must be written only to
`/data2/FreeToken/runs/dev_R055/reviews/E2-R055a-gate-D06_startup_review_v3.json`. It must bind
the R055a source SHA map, the dry-run receipt SHA, and the full dry-run source SHA map. It must not replace
the old R055 v2 review.

## Local validation

```powershell
python -m pytest -q development/tests/test_r055a_dry_run.py development/tests/test_r055_gate_d06_prepare.py
```

The active immutable R055a source passed Linux CPU validation: **19 passed, 1 deselected**.
The deselected legacy test calls the deliberately preserved old R055 `copy2` implementation;
the corresponding R055a override test passes with its read-only source and writable copy.
The original failing CPU evidence remains read-only; the final report is
`runs/dev_R055/r055a_real_path_evidence_v2/report.json`, SHA
`3c7db8e66c43f17a307c6e2843fb2bf793863b9342fffd3c1c40c54326e7e99a`.

Actual server file dry-run completed at host time **2026-10-07 04:57** as dell/uid1000, cwd
`/data2/FreeToken`: all six cold arms and fourteen PAUSE_ON files passed; no service, request,
lock, batch allocation or formal RID directory. Receipt SHA:
`ecb957c6bff33186021c0420517d6fa8cc61851500384b7f8dccffa088e54c2e`.
This is preparation evidence; formal GPU acceptance still requires independent R and D04.

The tests cover the new RID, no-run argument boundary, source copying before instrumentation,
post-instrumentation 0444 freezing, real writable probes, unique `.dryrun` placement, receipt
creation, dynamic port allocation, and prevention of repeat use of the same dry-run sibling.
