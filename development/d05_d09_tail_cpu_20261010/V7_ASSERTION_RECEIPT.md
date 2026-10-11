# D09 v7 assertion receipt

`strict_scheduler_d09_pinned_v7.py` completed fresh on remote FT venv with CUDA hidden. Before product construction it asserted:

- exact-input JSON SHA `b21a29e47d6dc5fb5be9d32e98bc446ed8a1f5d625efd7774aad31d2afdde6f9`;
- raw D09 round/config and donor/target binding hashes recorded in `FINAL_PINNED_RECEIPT.md`;
- exact-input schema and full source-binding dictionary;
- selected cell: boundary 20282, common prefix 20283, ordinary page floor 20224, prompt 21302, round 7, tail 1020, generation turn 21297, last markers `[20282,21297]`, and edit applied;
- donor/target int32 token digests.

After UID0 finished cache commit it asserted, not merely recorded:

1. exactly one successful native `snapshot_message_boundary`, with cached=20282, carrier snapshot=20282, and non-null carrier index;
2. exactly one native `_commit_d09_exact`, with boundary=20282, that same non-null index, ping-pong true, `old_cached=20160`, `old_is_d09=false`, and original return `false`.

Only the transparent observer delegates surround these original methods. The v7 result is `target_admission_cached_tokens=20160`.
