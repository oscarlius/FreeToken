# T04 / S-007 current-scope audit — 2026-10-08

## Authority used

1. `T04_E1-R003-tolcal_状态层容差独立标定.md` lines 3–21 is the newest 10-06 21:05 block and explicitly replaces conflicting body text. It makes S-007 a read-only, no-GPU analysis whose output is the four state categories' per-layer maximum-absolute and relative-difference distributions, with no release verdict.
2. `CODEX_HANDOFF_20261006.md:3,38` makes `PLAN_20261005_重新规划.md` authoritative, preserves §8.6 constraints, and repeats the S-007 scope: read E2-R002 plus four ordinary cold arms from E2-R036/R038, report four-state distributions only.
3. `PLAN_20261005_重新规划.md:94` says the legal-reorder envelope is record-only and cannot independently release a change; `:326,331` makes S-007 read-only and reserves (does not approve) E2-R053 only if a GPU supplement is needed.

## Result

| Reported gap | Required for current release / S-007 scope? | Evidence and disposition | Smallest next step |
|---|---|---|---|
| Historical B↔R4096 UID/input-ID mapping | No | The current card's required output is state distributions, not a four-way historical identity proof. S-007 has delivered four ordinary-cold distributions (296 points), their 128-token/full-text difference evidence, and two historical legal-reorder distributions (1,776 points). The result explicitly preserves the absent B↔R4096 mapping as a historical observation, not a verdict. | No GPU task. If a later T04-completeness decision requires it, first attempt a separately authorized, read-only metadata mapping. If the needed mapping was never recorded, request an E2-R053 collection authorization; reservation is not approval. |
| E2-R002 formal D04 closure | No, but E2-R002's independent read-only review remains distinct historical governance work | The latest card says E2-R002 is “待复核” and asks for independent review before using its records; it does not require changing its verdict or D04-closing it. The handoff demands analysis only, while §8.6 requires failed/old records remain append-only. `T04-S-007_20261008.md` correctly keeps R002 `pending_review` and gives no release claim. | Do not D04-close R002 under S-007. If governance later needs the historical round's verdict, assign a separate R/D04 review task with explicit authority; no GPU round is inherently needed. |
| Missing fixed-continuation logits | No for the newest S-007 deliverable and no release gate | PLAN §4.1 mentions state **and logits** for the broad legal-reorder envelope, but the newer, controlling T04 block narrows its concrete S-007 output to the four state classes. The handoff repeats that narrower output. PLAN §4.1 also says the envelope cannot alone support release. The 2026-10-08 result therefore properly records logits as an observation gap rather than a blocker. | No automatic collection. A later decision to complete the broader paper envelope needs a new explicit card/round assignment. If existing logits cannot be derived read-only, E2-R053 requires fresh authorization before GPU acquisition. |

## Evidence sufficient for current scope

The sealed read-only result reports all four requested ordinary-cold state distributions: 4×74=296 points, plus recomputed 4×128 physical-token/full-text differences; it separately reports 2×888=1,776 historical state points. The result remains distribution-only and does not issue a tolerance or release decision, matching the current card and handoff.

No new T04 GPU collection, D04 action, or release conclusion is authorized by this audit.