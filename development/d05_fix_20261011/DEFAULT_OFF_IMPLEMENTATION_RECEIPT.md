# D05 default-off implementation receipt

- **Base source:** `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`
- **Local isolated worktree branch:** `codex/d05-decode-align-481-20261011`
- **Source head:** `4df56f3bde582c96a605ac77811b6547c500e1cb`
- **Feature commit:** `d5e9dcc1bc98af49c2db245ffab2477e4a4a58b9`
- **Lifecycle regression commit:** `e6e879c73530c912f374eb25b5a229550aa6b36b`
- **Fixture correction:** `4df56f3bde582c96a605ac77811b6547c500e1cb`

## Behavior

`FREETOKEN_D05_ALIGNED_DECODE_STATE` defaults to false.  When true, the real
Scheduler `_forward` calls the hybrid cache's stream-ordered copy before the
next decode forward.  The cache keeps the latest aligned D05 boundary in its
existing two ping-pong slots; a pre-existing non-D05 track (tool anchor or
prefill checkpoint) is never replaced.  On a page-unaligned finish, the
ordinary hybrid cache finish path donates that aligned frozen state.

The CPU lifecycle fixture uses UID 8 at P=13504 then an unaligned finish at
13554.  It checks conv, recurrent, and PLE slot-state restore, two independent
readers' page and mamba references, and LRU mamba eviction.  The same real
`Scheduler._forward` fixture checks the default-off path from pre-forward
13375 to original page-aligned 13376 finish.

## Source blobs

- README.md `f223029a2d108a66caec9a1de67cc8c6deb58b1d`
- python/freetoken/env.py `5e473b3ff5d395cf2131e235ae6e8ac55c86a4aa`
- python/freetoken/core.py `71f01a70e8a0bd761b79b947e8afa8c6a0bd01c8`
- python/freetoken/scheduler/cache.py `3857c801ce696e5bb6750ec275003ae6cf2e228e`
- python/freetoken/scheduler/scheduler.py `9cda76a471cda322d87c07e4472c30a10af2ec3e`
- tests/scheduler/test_hybrid_cache_manager.py `9f6e9ccf67b950c6ee5d987c6797e06fe01aba45`

## Verification state at GPU_BEGIN

- Local `py_compile` and `git diff --check` passed after the fixture correction.
- An isolated remote CPU-only run (CUDA hidden, OMP/MKL=1) passed 15 existing
  hybrid-cache tests before the new lifecycle test was added.
- The only subsequent CPU run stopped after one fixture geometry failure:
  `Req` correctly requires `cached_len < len(input_ids)`. Commit `4df56f3`
  corrects that fixture to pre-forward 13375 then finish 13376.
- GPU_BEGIN arrived before a rerun. No remote CPU/GPU process, service, API, or
  build may be started until root sends GPU_END. Thus the fresh 16-test result
  is pending, not claimed.
