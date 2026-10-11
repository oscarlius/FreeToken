# D10 T16 tooling v3/v6

`d10_t16_full_runner_v3.py` is the versioned D10 adapter for the existing
`E2-D10-T16-night-20261010` candidate. It delegates parsed-argument comparison
to the pinned base `strict_args`, which permits only a valid generated
`_unique_suffix` PID change plus `d10_staggered_decode=False`; business
argument changes remain failures.

`d10_owned_launch_v6.py` binds that adapter and uses v2 dry-run, startup-review,
and user-scope approval paths so it cannot consume the former v2/v5 records.
`--filedry --card D10` is CPU-only mock evidence for eight arms and 96 planned
calls. It starts no GPU, HTTP service, compiled extension, or formal T16 round.
Independent review is required before any `--run` path.
