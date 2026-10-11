# D05 default-off CPU verification — 2026-10-11 01:57 CST

## Scope and source identity

- Local isolated 481 worktree head: `6e0ae8f467ab60eb068464d88f6cf176c66b9d25`.
- Remote isolated worktree: `/data2/FreeToken/wt/d05-decode-align-481-20261011`.
- Remote equivalent applied head: `181a510c56ad36265ccc655fc0cebc7304c4e4e9`; clean `git status --porcelain`.
- Base: `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`.
- Sync delta mbox SHA-256: `01f3320d4e4f577325154bab3ed5149763c32453933e1fdb5ca84ce8045f905d`.

Remote file SHA-256:

| File | SHA-256 |
|---|---|
| README.md | `7caf25b3279c54ff5ed4f5a4bbb69ee5aaf33152aa30300865b0c05655800eca` |
| python/freetoken/env.py | `7d789be72c55b628d381c4ebe923e618067fb96f68b306e2a33d5105fd5544dd` |
| python/freetoken/core.py | `9f792de1c95034f72ccbc5a1477d33513f502a02f133c131f6181db4a3232a90` |
| python/freetoken/scheduler/cache.py | `a1bc3e91608c3f4c0c4b8c9c29f910128820a90dfbd58f16a719f490c511e9c4` |
| python/freetoken/scheduler/scheduler.py | `63a759ebc9f6dbde6c62663f725b6126ddb3906fd77637db6fe1e17da282c200` |
| tests/scheduler/test_hybrid_cache_manager.py | `dcf25d87c0acc4c2520265251681d6e76b9b1b6b41d3ab8622d08346621a89cd` |

## CPU-only command and result

```bash
cd /data2/FreeToken/wt/d05-decode-align-481-20261011 && \
  env PYTHONPATH=/data2/FreeToken/wt/d05-decode-align-481-20261011/python \
  CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /data2/FreeToken/venv/bin/python -m pytest tests/scheduler/test_hybrid_cache_manager.py -q
```

Result: **16 passed, 1 warning in 3.55s**, exit 0. The warning is Triton CPU fallback. Full captured stdout is `REMOTE_CPU_PYTEST_20261011T0157.txt`, SHA-256 `a7b929fdb4f5d2b1eb696f7f5b9d2a0d0ff0131f218716337f041df8a75cc8bc`.

No GPU, API, model service, or push was launched by this verification.

## Claims tested

- With `FREETOKEN_D05_ALIGNED_DECODE_STATE=true`, real `Scheduler._forward` performs the stream-ordered snapshot at UID 8 / P=13504 before the model seam calls real `Req.complete_one`; the unaligned 13554 finish restores the P state, including conv, recurrent, and PLE state arrays.
- The frozen snapshot survives two independently locked readers, restore copies, page/mamba reference release, and ordinary mamba LRU eviction.
- With the flag false, the real `_forward` + real `Req.complete_one` preserves the original aligned 13376 finish-donate behavior.

## v6 carrier boundary

The fixture binds `strict_scheduler_d05_pinned_v6.py` SHA-256 `aec28686989179bae8f3369aeb37044d8490e0bda94af41418b7eec3c61995d9`, target carrier bytes SHA-256 `1dd6711b108d018c3fee019657b98055cc667dc126e3aa53c7b13e2c5eae18b5`, donor carrier bytes SHA-256 `74bca9854a36f022b5c7ec8b959c9f5acee39550aefad97ed7a39a79e33470a3`, and the v6 13504→13554 / 13375→13376 splits. Historical v6 explicitly labels its `torch.arange` carrier as geometry-only; this test does not claim raw R052a token-content binding.

This is CPU ownership/bookkeeping evidence. GPU numerical equivalence and the separate T16 gate remain unexecuted.

## Addendum — commit identity, canonical source identity, and explicit fixture receipt

The local and remote commit IDs intentionally differ: local head is
`9d869d77fcb4da6a1c64fcbae419018a03aa36e4`, whereas remote head is
`730b58c96527fe5bf117d1f3c2430e405173d28b`. The remote isolated worktree
received the four local commits through `git am --3way`; Git creates new commit
objects because the applied commits have different parent/committer metadata.
This is not represented as a same-commit claim.

Both histories have exact merge-base
`481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`. The canonical Git blobs are
identical on both sides:

| File | Git blob |
|---|---|
| README.md | `4fdee4effc761a71bed794d4e5814feaebf80976` |
| python/freetoken/env.py | `5e473b3ff5d395cf2131e235ae6e8ac55c86a4aa` |
| python/freetoken/core.py | `71f01a70e8a0bd761b79b947e8afa8c6a0bd01c8` |
| python/freetoken/scheduler/cache.py | `3857c801ce696e5bb6750ec275003ae6cf2e228e` |
| python/freetoken/scheduler/scheduler.py | `9cda76a471cda322d87c07e4472c30a10af2ec3e` |
| tests/scheduler/test_hybrid_cache_manager.py | `6ccc85be691f2bf2b8502dfbec9db6fc14850f20` |

Raw checkout SHA-256 differs because the local Windows checkout uses CRLF and
the remote Linux checkout uses LF. The canonical Git blobs above prove the
committed source is identical after Git's line-ending normalization.

A second CUDA-hidden run used `pytest -qs` and emitted:

`D05_V6_BOUND_RESULT enabled_cached=13504 enabled_finish=13554 enabled_state_assertions=conv,recurrent,ple default_off_cached=13376`

It passed **16 tests** in 3.60s, exit 0. Full stdout is
`REMOTE_CPU_PYTEST_20261011T0200_EXPLICIT.txt`, SHA-256
`4a9246abfc47d9ccaf9ac483d06d2517d7b423d852f98872397f43c296b0b07c`.
This is test-scope CPU evidence: it proves the specified bookkeeping assertions
inside the fixture, not GPU numerical equivalence or T16 acceptance.
