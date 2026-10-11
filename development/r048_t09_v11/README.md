# R048b / T09 v11 preparation

Local source preparation only. This package does not grant a GPU retry.

Candidate `76af7584d7595d9cc52dcd60deff3aacdae1d9d6` fixes capture-time observation and preserves CUDA Graph execution. Runtime worktree: `/data2/FreeToken/wt/e2d08-capture-trace`. The new `E2-R051a-gate-D08` must be `kept` and its canonical metadata must bind this candidate and parent `effb9969706922ddad9e59b96377e46469ebe97f`. Old R051 acceptance alone is rejected. R048/R048a failures and prior queue metadata remain required.

V0/A/B/C/S each retain separate performance and diagnostic services, 98,304 / 0.88, ordinary prefill 4096 and the existing physical-memory exception for C. Every new comparison uses this round's own V0; no b106 measurements are reused. There are at most ten services and sixty requests.

The diagnostic consumer requires all 48 hybrid layers in every consecutive decode-observation sequence, genuine positive native clocks, fresh task completions, finite CUDA-event timings and at least two graph replays. Python enqueue timings must be absent on replay. The layer count is pinned to the actual model config SHA `deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80`; CPU-only layer routing is refused. Product engine/graph sources join the source closure.

Local tests: `python -m pytest -q tests` gives 52 passed and 12 POSIX-only skips. Tests include the actual candidate observer and JSON writer feeding the actual v11 trace consumer, malformed/stale/incomplete observations, actual service argv and the retained real CLI-wrapper contract. `FT_CPU_CANDIDATE_SOURCE` can select the exact candidate worktree for Linux testing; local default is the adjacent `e2d08-capture-trace` checkout.

Linux tests, native artifact reuse provenance, default-path FILEdry and independent startup review remain pending. FILEdry's admission still requires the new T16 gate; do not bypass it to claim readiness. Any GPU execution also requires explicit user approval under HANDOFF section 8.4 after the measured R048a failure.
