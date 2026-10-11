# D05 v2 value assessment — blocked before implementation

## Scope and stop condition

This is the directive-v2 prerequisite only. The directive SHA-256 is `ce215b6a9d1a88d03f9b46e205179206b1c0409dd63730936d54d84a0adfe73d`. The requested comparison requires a real generation's ordered native IDs, API assistant fields, the following actual client message list, and token IDs produced by the 481 template for that following prompt. No source worktree, product edit, remote CPU run, GPU action, service, or HTTP request was made.

## Evidence searched

- `development/d10_reanalysis_20261010/closed_loop_20261010/raw_d0_2308/service/observer/tokens.jsonl`, SHA-256 `50270d507e966ed79849734627758cacbb4c3a7cebedd29796dd534cf2ade824`: genuine native `next_token` records, but indexed only by service UID.
- `development/d10_reanalysis_20261010/closed_loop_20261010/raw_d0_2308/metrics/d0/Y/profile_export_raw.jsonl`, SHA-256 `acae16c101130554856ae5511de562edb6c4807f619940a9be9bb53d2b588da3`: API SSE packets with both `content` and `reasoning_content`, but no following conversation turn/template-ID receipt and no direct binding to the observer UID.
- Local R046g closure/route files: no local `tokens.jsonl` or equivalent ordered native generated-ID array was found. The sealed trace paths point to the remote shared run; no remote read was performed in this lane.

## Three required cases

| Case | Status | Reason | Reusable tokens |
|---|---|---|---:|
| body only | unavailable | no same-generation native-ID → next-client-messages → template-ID chain | unavailable |
| reasoning content | unavailable | native IDs are UID-only; no request-ID/next-messages/template-ID binding | unavailable |
| tool calls | unavailable | no tool-call API delta and no native-ID/next-messages/template-ID chain | unavailable |

The values are intentionally **not zero**. Re-tokenizing API/SSE text would invent the missing native IDs and is prohibited by v2.

## Decision

`BLOCKED_NO_VALUE_DECISION`: none of the three cases meets the preregistered evidence contract, so D05's value cannot be established. Per the value-first gate, no 481d3a7 worktree was created and no default-off D05 implementation began. A later independent evidence acquisition may reopen this lane only after it supplies one or more complete four-artifact chains.

## Implementation design note, not an implementation

If the gate is later satisfied, the state location is GPU-resident ping-pong slots in the 481 `LinearStatePool`; state movement would be one device-to-device copy at most per 64 decode tokens, capturing conv, recurrent, and declared PLE slot state at P. Exact byte count and measured decode overhead remain unmeasured preconditions; the 1% enabled-path budget is only preregistered.
