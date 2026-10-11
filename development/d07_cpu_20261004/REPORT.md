# D07 CPU validation

- Staging: `/data2/FreeToken_d07_cpu_20261004` on `172.16.108.9`.
- Source package SHA-256: `b2f40928a7c2974084555666f11815f3566245815dec1702cc4363a6d25b6679`.
- All 13 source files matched the transferred SHA manifest before testing.
- The venv `.pth` inserted the old source tree before `PYTHONPATH`; validation
  therefore used `/data2/FreeToken/venv/bin/python -S runner.py`, with the
  staging `python/` inserted first and venv site-packages appended explicitly.
- Environment: `CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=4`,
  `MKL_NUM_THREADS=4`, `PYTHONDONTWRITEBYTECODE=1`.

## Result

`tests/layers/test_route_trace_guard.py`,
`scripts/tests/test_agent_trace_route_evidence.py`, and
`scripts/tests/test_route_analyze.py` completed with **15 passed in 1.40s**.
The complete remote output is retained in `d07_cpu_pytest.log`.

This is a CPU source-staging check only. It does not establish a formal Git
candidate, GPU D2H behavior, CUDA graph behavior, or a production deployment.
