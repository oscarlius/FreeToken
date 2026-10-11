# Final pinned CPU replay receipt

Date: 2026-10-11. CPU-only; no GPU, service, HTTP client, or product source mutation.

## Product source pin

Both v6 scripts assert their imported `freetoken.__file__` is beneath `/data2/FreeToken/wt/d05_hbug_candidate_20261010/python`, assert worktree HEAD `bd57cfdccc2a935d46cb0a89b8b36be7a18706de`, and compare disk file hashes against the HEAD git blobs. The emitted receipt covers `scheduler/cache.py`, `scheduler/scheduler.py`, `core.py`, `kvcache/linear_state_pool.py`, and `attention/linear.py`, plus byte hashes for the exact called product functions. It fails before replay on any import/root/HEAD/blob mismatch.

Fresh runs:

- `strict_scheduler_d05_pinned_v6.py`: real donor and target each advance through real `Scheduler._forward`; result `cached_tokens=13376`, target post-forward `13554`.
- `strict_scheduler_d09_pinned_v6.py`: raw-sealed token IDs; result UID1 `match_req=20160`; transparent receipt shows `snapshot@20282=true` and original `_commit_d09_exact(...old_cached=20160...) -> false`.

## D09 raw/source/input pins

| Artifact | SHA-256 |
|---|---|
| round.json | `a6655b5920069ada590f515dc0a612e8fb65b33045c48ba56021b235b4750ee5` |
| split config.json | `4454e172b679a7aed0731ec8f32e18364cf052fe7cfebe1cdbdeb02550450480` |
| exact token payload | `b21a29e47d6dc5fb5be9d32e98bc446ed8a1f5d625efd7774aad31d2afdde6f9` |
| donor binding | `3bfc9c87456929f594666b171c5cfb4f899e90afb0077e4980b9feca9ca37568` |
| target binding | `818b87b48328070aecbdfa530ce7521383d122f510c7cdf0f9d7d6712ba455fb` |
| hot observations | `8b35ac3a6a246aacb8bbcfc3119bbcf5ec11d312e92377bd385d600718fb2eef` |

Token-array validation inside D09 v6 binds donor input SHA `24068f95180ac5cca644024d56f749a341df16ceb35574e41c83bb396471142a` and target input SHA `22ed510abb88eaaac15e6103fe292ba23d641e18ea01c14fa1f2dce6c4790fbc`.

## D05 input qualification

The D05 v6 cache prefix is the synthetic `torch.arange` geometry stand-in inherited from the expressly permitted old R052 replay method; it is **not claimed to be raw R052a token content**. Its only assertion is cache-prefix bookkeeping geometry: aligned donor 13376, target final 13554, page floor 13504. Existing R052 source manifest is retained separately; no readily available frozen raw R052a token array was introduced or represented as bound input here. This confines the D05 result to product-path geometry replay, while D09 is token-content-bound.
