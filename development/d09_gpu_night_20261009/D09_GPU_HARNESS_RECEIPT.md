# D09 GPU Harness Receipt

- Recorded scope: CPU preparation only; no GPU, HTTP, service, compilation, NVCC, or JIT.
- Candidate binding: c17b69a46cd512fbf3d127d3879bce92caae457b.
- Prediction binding: edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9.
- FILEdry passed with config digest 3b0436512252bb16566df53e75920cf43959a26665c215f899c280a5822591f3.

The runner has a CPU FILEdry mode and an actual process-group-owned --run path. --run refuses to act absent a root-sealed admission with this config digest, RID, and explicit command; it creates a new owned run directory and writes terminal status after cleanup. The config binds T16 default-off, T17 exact 20282/1020 and 22558/197, T03b, and T2 sequence. R067d real terminal evidence remains an explicit dependency for any tail<=64 assertion.
