# D05 value pre-registration (v2)

- Directive: `plan/D05_D09_FIX_DIRECTIVE_20261011.md`, SHA-256 `ce215b6a9d1a88d03f9b46e205179206b1c0409dd63730936d54d84a0adfe73d`.
- Baseline for any later implementation: `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`; no dependency on bd57 is authorized.
- This pre-registration is CPU/local evidence only. It does not claim a GPU measurement, template result, or product behavior.

## Value test contract

For each of `content_only`, `reasoning_content`, and `tool_calls`, acceptance requires all four bound artifacts for the **same real generation and following turn**:

1. ordered native generated token IDs;
2. original API assistant fields (`content`, `reasoning_content`, `tool_calls`);
3. actual next-client `messages` built by returning those fields unchanged;
4. 481 chat-template token IDs for that next prompt.

The result is the suffix length of the prior prompt plus native generated IDs that is a prefix of the next prompt IDs. Text/SSE re-tokenization is forbidden as a substitute for item 1. A missing item is `unavailable`, never zero.

## Snapshot-cost pre-registration (only relevant if value is usable)

The proposed implementation location is a GPU-resident ping-pong slot owned by the native cache/state pool. At decode positions crossing the final 64-token boundary P, copy the real conv, recurrent, and PLE state exactly once per 64 generated tokens; promote only the P state at completion. Host staging is rejected because it introduces PCIe transfers of multi-layer state and a multi-millisecond synchronization risk.

Before implementation, the exact state byte count must be read from the 481 state-pool structures and recorded. The enabled-path budget is no more than one device-to-device copy per 64 decode tokens and no more than 1% decode-rate loss; neither amount is asserted as measured here. The feature remains default-off and requires separate CPU, non-author review, and later separately authorized T16 GPU gates.
