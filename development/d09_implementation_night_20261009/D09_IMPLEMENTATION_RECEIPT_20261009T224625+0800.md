# D09 implementation receipt

- Recorded: 2026-10-09T22:46:25.8286184+08:00
- Local worktree: `development/e2d09-message-boundary-v1`
- Base: `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`
- Committed candidate: `47d9b5c9885c8b1c3fdced0d75fc0b32c0fdaa51`
- Prediction seal consulted, not modified: `d09_prediction_20261009/CURRENT_PREDICTION.json`, file SHA-256 `edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9`.

## Implemented scope

- New default-off `--enable-message-boundary-ckpt` flag.
- Runtime derives one boundary only from the immediately preceding literal single-token `<|im_start|>` before the final generation header in the actual rendered token ids.
- Eligibility is `boundary >= 8192` and `generation_header - boundary <= 1024`; unsupported templates have no marker and remain inactive.
- The prefill path cuts at that one boundary, snapshots the live GDN state into the existing #577 ping-pong slot, preserves it through the tail, and donates it before the final live state at finish.
- The D09 snapshot blocks ordinary tracking from overwriting its one allocated slot. No new host bank, arbitrary multi-anchor cache, `prompt-cache-tail` CLI, release/e2 change, service, or GPU action was introduced.

## CPU evidence

On `172.16.108.9`, dedicated worktree `/data2/FreeToken/wt/d09-message-boundary-v1`, FreeToken venv:

```text
PYTHONPATH=python pytest -q tests/scheduler/test_hybrid_cache_manager.py tests/scheduler/test_prefill_anchor_cut_switch.py tests/scheduler/test_switch_defaults.py tests/scheduler/test_anchor_cut_scheduler_wiring.py
28 passed in 4.20s
```

`python -m compileall -q python/freetoken tests`, `git diff --check`, and clean-tree check also passed there. The local Windows system Python lacks project `flashlib`, so its pytest collection cannot substitute for the remote FreeToken-venv result.

## Required GPU acceptance (not run)

- T16 default-off bitwise contract.
- T17 same-structure equivalence with the new D09 split.
- R067d result before interpreting tails of 64 tokens or less.
- T03b edit replay and Agent T2 reverse-cold, ascending-warm, and edit passes, comparing first non-empty delta against the sealed 2.8 s prediction.
