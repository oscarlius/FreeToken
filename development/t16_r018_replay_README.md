# R018 archival CPU replay

`t16_r018_replay.py --round-dir <E2-R018-gate-D03>` is read-only. It restores
the archived runner/base bytes under their canonical sibling names in a private
temporary directory, runs only its CPU self-test, then recomputes fulltext,
prefill, event and H2D/D2D-source inventory from all eight archived arms.
It does not run a resource gate, model, GPU, server, or `--run` path.
