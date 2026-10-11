# T17 v7 independent CPU startup review

**Verdict: APPROVE_CPU.** The v7 delta is limited to setting `SO_REUSEADDR` before binding and retaining each socket before its bind, plus a fresh v15 FILEdry directory. Its local and remote SHA-256 is `518bc4ee820ac0366660145f02209b875c9a8f24e253e0ceee17dca4d48216f1`.

On Linux, `CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest /data2/FreeToken/development/night_execution_20261009/test_d09_port_reuse_v1.py -q` passed 2/2. It proves that an active LISTEN still blocks both reservers, while a server-side TIME_WAIT blocks a plain bind but permits the explicit reuse path.

`evidence_cpu_filedry_v15/e2e_terminal.json` has SHA-256 `f4dfbd288c891c38f881b694a371d1744c101d4bd07d0952f386ad4fab6d34a5`. It records 6 cleaned arms, 8 calls, sealed-T16/controller/child/atomic-receipt bindings, completed post-cleanup rebind, and released task lock. All 70 terminal-listed artifact hashes recomputed cleanly. The unsafe lock-retention path is unchanged by the v6-to-v7 delta; the retained targeted v6 regression passed, including injected `OSError` and assertions for retained lock, `failed_harness` receipt, and absent terminal.

The Windows run of the Linux TCP test is deliberately not evidence because Windows `SO_REUSEADDR` permits the concurrent bind. This review did not start GPU, a model service, HTTP, or native compilation. The FILEdry terminal explicitly reports `product_acceptance: false`; formal T16/T17 GPU gates remain open.
