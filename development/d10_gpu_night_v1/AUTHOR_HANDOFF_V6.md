# D10 author handoff

`d10_t16_full_runner.py` is an isolated D10 adaptation of the pinned D09 T16 protocol. It retains the protocol's 8-arm comparison and lifecycle, binds base `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`, candidate `22ff3a389eae3724cdca9a45f2e19577082a2032`, RID `E2-D10-T16-night-20261010`, and permits only `d10_staggered_decode=False` as the parsed default-off delta. It validates the candidate `args.py` SHA and the flag/ServerArgs field before runtime.

`d10_aiperf_runner.py` reads the actual R045 retry1 wave command. It binds `request-count=2` and `concurrency=2` for two profiles (four AIPerf requests), and binds the frozen `inputs_ignore_eos256.jsonl` SHA `a1fcedff4ec4d70ca8ecdebf2e704fc30475600ff668177f3715f11d569e64a5`.

CPU evidence: adapter self-test passed; AIPerf FILEdry passed; `test_d10_aiperf_runner.py` passed. No GPU, service, HTTP, JIT, NVCC, or compilation was used.

Current admission blocker: remote read-only inspection found that `/data2/FreeToken/wt/d10-staggered-v1/python/freetoken/kernel/` lacks both candidate extension files, while the base has verified `_cpu_moe` and `_pinned_tensor` bytes. This package records the actual base hashes/sizes and candidate absence, but does not mutate the candidate worktree. A root-owned decision is required to provide verified identical extension bytes in the candidate execution environment before `--run`; otherwise the pinned runner correctly fails compiled-extension validation.

No independent-review file was created or changed.
