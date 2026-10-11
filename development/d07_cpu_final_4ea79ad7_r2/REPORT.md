# D07 final CPU source-staging validation

Staging: `/data2/FreeToken/runs/dev_D07/cpu_final_4ea79ad7_r2` on
`172.16.108.9`.

The archive contained the 13 D07 changed files plus the read-only parent
dependency `scripts/multisession_probe.py`, required by the analyzer's actual
two-decode integration case. Before execution, the archive SHA and all 14
manifested paths were verified on the host.

The venv `.pth` would otherwise resolve FreeToken to its old source tree. The
runner used `/data2/FreeToken/venv/bin/python -S`, inserted staging `python/`
first, and appended only the venv site-packages directory. It printed:

`SOURCE /data2/FreeToken/runs/dev_D07/cpu_final_4ea79ad7_r2/python/freetoken/__init__.py`

Environment: `CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=4`,
`MKL_NUM_THREADS=4`, `PYTHONDONTWRITEBYTECODE=1`.

Command target:

`tests/layers/test_route_trace_guard.py`
`scripts/tests/test_agent_trace_route_evidence.py`
`scripts/tests/test_route_analyze.py`

Result: **27 passed, 1 skipped in 3.68s**. The skipped test is the explicitly
serial-GPU-owned CUDA D2H abort case. This evidence does not establish a Git
candidate, GPU behavior, or deployment. README changes after this run are
documentation-only and do not alter the executed Python source manifest.
