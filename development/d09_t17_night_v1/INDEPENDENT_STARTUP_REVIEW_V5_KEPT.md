# T17 v5 kept-admission implementation handoff

- Scope: `d09_t17_runner_v5.py` and `test_d09_t17_runner_v5.py` only. Historical `v4_kept` and its review remain unchanged.
- Runner SHA-256: `acbe59559a637b255f68f4264ea8194c867042fe47adacf3b5fdb49625461085`.
- Execution boundary: CPU FILEdry only. No GPU, model service, HTTP request, compilation, or candidate mutation occurred.

## P0 corrections implemented

1. The live child now stops the owned group, requires GPU idle, atomically rebinds and releases both configured ports, and writes one `post_cleanup_rebind.json` per arm. If this fails, it writes `unsafe_cleanup.json`, retains the D07 lock, and exits nonzero; it cannot write a closed terminal.
2. FILEdry calls the production `controller()` and `child()` functions with task-owned fake D07/lifecycle/transport dependencies. It validates the sealed T16 `kept` round plus manifest hashes, source/native provenance binding, atomic launch receipt and child binding, task lock ownership, six fake child processes, eight fake transports, per-call receipt/response/observations, cell comparison, port rebinds, and post-cleanup lock release.

## Fresh CPU evidence

- `python d09_t17_runner_v5.py --filedry` produced `evidence_cpu_filedry_v12/e2e_terminal.json`: 6 cleaned arms, 8 calls, two stable cold A/B cells equal to hot, `post_cleanup_closed: true`, and `gpu_lock_released: true`.
- `python -m pytest -q test_d09_t17_runner_v5.py` passed 2 tests. The second injects a post-cleanup rebind failure and proves the task-owned lock remains, `unsafe_cleanup.json` exists, and no `e2e_terminal.json` is written.

## Review status

This is implementation and CPU evidence, not an independent approval. `independent_review_required` remains true, `product_acceptance` remains false, and no GPU T17 round may start from this artifact without root admission and independent review.
