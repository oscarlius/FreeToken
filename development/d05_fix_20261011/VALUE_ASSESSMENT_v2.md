# D05 v2 value assessment — superseding the initial local-only inventory

This document supersedes only the `BLOCKED_NO_VALUE_DECISION` in `VALUE_ASSESSMENT_BLOCKED.md`. That earlier result incorrectly treated a historic next-message/template-ID receipt as a prerequisite. Directive v2 instead requires this assessment to construct the next client messages from the real API fields and render them through the actual 481 frontend.

## Method and binding

Remote CPU-only, with `CUDA_VISIBLE_DEVICES=''`, `OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, read the sealed D0 artifacts. No GPU, service, HTTP request, compilation, or source mutation occurred.

The 481 path was the actual `freetoken.tokenizer.tokenize.TokenizeManager`, not direct `AutoTokenizer.apply_chat_template`. The direct HF call was rejected: it yielded two tokens and did not equal the observer input. `TokenizeManager` uses the deployed DSV4 encoder and matched both observer inputs exactly.

For each Y request, the unique `usage.prompt_tokens` value binds profile raw request to observer UID; its exact `completion_tokens` equals the counted native token records. API SSE deltas were concatenated into the assistant `content` and `reasoning_content` fields, then appended unchanged to the original messages, followed by a deterministic next user turn (`Continue.`). The chosen next user text appears after the assistant history and does not affect the prefix through the assistant response.

## Result

| Case | UID / request | Actual API fields | Native output IDs | 481 previous prompt equals observer | Preserved native decode IDs |
|---|---|---|---:|---|---:|
| reasoning + body | 2 / `174dbe02-8e1d-4a6b-98a6-e8a1853f4518` | content + reasoning_content | 46 | yes | 46 |
| reasoning + body | 3 / `4427308c-a2f7-4215-ace6-b851c1e0177b` | content + reasoning_content | 58 | yes | 58 |
| body only | — | no qualifying real body-only generation identified | — | — | unavailable |
| tool calls | — | no qualifying real tool-call generation with native IDs identified | — | — | unavailable |

The two verified cases establish non-zero D05 value: their full native decode suffixes survive a true API-to-client-message-to-481-template reconstruction. They are short closed-loop prompts and do not quantify the R046g eight-round distribution; that remains an evidence gap, not a zero result.

Machine-readable receipts are `REMOTE_D0_TEMPLATE_VALUE_v2.json` and `STATE_GEOMETRY_481.md`.

## Decision

`VALUE_GATE_NONZERO_FOR_REASONING_PLUS_BODY`. The directive's zero-value stop condition does not apply. Proceeding to a separate 481d3a7 worktree and default-off implementation is allowed, subject to the stated CPU tests and independent review. The body-only and tool-call cases remain unavailable and must remain explicitly reported in any later acceptance material.
