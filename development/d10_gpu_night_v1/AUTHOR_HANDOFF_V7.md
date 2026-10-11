# D10 GPU acceptance tooling handoff v7

Runner: `d10_t16_full_runner.py`, SHA-256 `c01a6a29e0a00d096e35c8f487319951054ee1f9e231df17c8d89205b10e8592`. It is the isolated 8-arm D09-T16 protocol adapter, retargeted to base `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`, candidate `22ff3a389eae3724cdca9a45f2e19577082a2032`, RID `E2-D10-T16-night-20261010`, D10 `args.py` source SHA, and only `d10_staggered_decode=False` as a parsed delta.

AIPerf FILEdry runner: `d10_aiperf_runner_v2.py`, SHA-256 `6e1f6025c8a4741e0a3488abeee4b2095438ed7dcc8c1440b55f8c13c5ccf0b7`. It embeds the frozen R045 retry1 command record SHA `5f04c7d0547e66f907db625194b0ea6bb55cc765663f114282124928e0cdd7e4`, binding two profiles of request-count 2/concurrency 2 (4 AIPerf calls) and the ignore-eos-256 input SHA.

Local and remote CPU runs passed adapter self-test and AIPerf FILEdry with GPU/service/HTTP false. The direct runner denies execution absent root-owned admission; it is not a production verdict.

P0 run-admission gap found by remote read-only inspection: the D10 candidate worktree has no `_cpu_moe` or `_pinned_tensor` candidate files. The base hashes/sizes are recorded in `d10_native_provenance_v1.json`; no candidate mutation, build, or copy was performed. Root must provide a verified execution-environment strategy for those identical bytes before actual `--run`, or the protocol correctly fails native validation.
