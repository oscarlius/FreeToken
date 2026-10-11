# GDN operator replay preparation and independent review

The actual Linux stage is
`/data2/FreeToken/runs/dev_D14/gemm_e1154756dd3c`, with CPU report SHA-256
`dcbb21c2df0b49cdd25311375431f6f7250ce8b6873688c8d8a38ba4faf55e56`.
The independent verifier approved one owned GPU diagnostic after reading the
actual stage, source hashes, logs and plan. All 17 runtime/plan sources are
read-only and bound to the launch receipt.

Linux validation passed 13 replay tests, 10 original gate tests, compilation
including the monitor/reader programs, and real CPU preparation. Preparation
loads the four BF16 GDN checkpoint parts in loader order `qkv,z,b,a` into
`[16480,2560]`, raw tensor SHA-256
`4be850f53b884949b3b9cb74675f0066d78e53e1ff3a58b117dcda5d125c205d`,
imports the bound `TorchLinearKernel`, and verifies CUDA remains uninitialized.
The recorded R030 warm/cold 64-row inputs are byte-equal. Config, index, full
shard integrity, raw safetensors header and candidate loader source are pinned.

Two earlier stages remain read-only: `gemm_a2cf460025b5` failed on the legitimate
overlay index symlink; `gemm_60a68010cd28` failed on incorrect test-fixture
basenames. They reserved no round and started no GPU execution. Their actual
logs and source hashes are retained in the corresponding local failed-CPU
receipts. Windows skipped the symlink tests; the final Linux stage exercised
them successfully.

The real launch assigned `E2-R031-diagnostic-T17`, batch 59, PID/PGID/SID
`774939`, birth tick `122960640`. The initial host observation verifies the
live process, exact command, recorded birth identity and global lock owner.
This is an operator-only replay, with no serving process. The root runner
sets GPU 0 only after owning the lock and batch process. It tests M3585,
M3649, M4096 and 64 separate M1 calls, saving three repeats of each output.
The remaining full-M input rows are explicitly artificial zeros.

R023 remains `not_met`. This diagnostic does not grant T17, E2-base.1, T10,
performance, past runtime-weight identity or sole cuBLAS-cause acceptance.
