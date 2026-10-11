# morning_restore04 independent CPU/code review

Reviewed at `2026-10-10T12:32:19.4398729+08:00` by a non-author reviewer. Verdict: **PASS_CPU_CODE_REVIEW_ONLY**. This is not deployment approval; `conditions_met` remains `false`, the root review remains `PENDING`, and `ROOT_FINAL_REVIEW.json` is absent.

`SOURCE_MANIFEST.json` contains and binds all 12 source files. Each file's local SHA-256 equals its manifest entry. Comparing the 03 and 04 manifests found the same twelve names; after the three explicit identity replacements below, each pair is byte-equal. A scan of the 04 tree found no retained `-03` identity.

- `morning_restore03_20261010` to `morning_restore04_20261010`
- `RESTORE481-MORNING-20261010-03` to `RESTORE481-MORNING-20261010-04`
- `ROLLBACK184-MORNING-20261010-03` to `ROLLBACK184-MORNING-20261010-04`

The 03 driver receipt records a prior `--execute` at `2026-10-10T12:19:51.118964+08:00`; 04 has a separate approval, rollback, and run identity, with one permitted attempt and no same-candidate retry. The remote source-manifest SHA is `b8be40ef306f5e8e1acd3b4e701d4c2e587e8737d5602e088a76a9cc0cff044c`.

Remote hash checks match the approval: frozen OPS binary manifest `a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18`, frozen OPS source manifest `029add4d8ca253ae64a8a34350f2287ab9e72acd631f049cc362d7e4921d5429`, and df77 cold baseline `df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97`.

On `172.16.108.9`, using `/data2/FreeToken/venv` with `CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, `python -m unittest -v test_cpu_orchestration.py` passed all 7 tests in 0.005 seconds. The test suite's subprocess runner is a stub; it recorded no service, GPU, lock, HTTP, smoke, rollback, or observer action.

The tested failure contract calls `stop_approved_restore.py` before `start_approved_rollback.py`; a stop failure blocks rollback. The approval scope also requires that after any smoke failure, later GPU work is prohibited. Root must perform and bind any final approval before this package can execute.
