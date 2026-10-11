# R052 cache-evidence CPU review — 2026-10-07

## Verdict

- **PASS (CPU semantic repair only).** The revised evidence path correctly accepts an OpenAI response that legally omits `prompt_tokens_details` for a zero cache hit, uses the actual Chat Completions SSE `chatcmpl-<uid>` identity to bind D0 rows, and uses D0 admission evidence for the final cache decision.
- **No formal R052 approval.** This is neither the required formal file-dry nor an R startup signature, and it does not establish GPU/model behavior, real request output, or a T11 classification result. GPU remains stopped after R046b's 98,304/.80 OOM.

## Acceptance criteria and evidence

| Criterion | Result | Direct evidence |
|---|---|---|
| Omitted API cache detail is legal for a zero hit | PASS | `strict_usage()` returns `None` when `prompt_tokens_details` is absent and rejects malformed supplied details (`r052_t11_replay.py:56-68`; regression `test_missing_api_cache_detail_is_preserved_as_none`, `tests/test_r052_t11_replay.py:71-78`). Upstream response serialization omits this object at zero (`e2base1/python/freetoken/server/openai_api.py:644-654`). |
| SSE Chat Completions UID binds D0, including first chunk of the same RID | PASS | `stream_uid()` requires one `chatcmpl-<integer>` value and rejects conflicting SSE/dev IDs (`r052_t11_replay.py:71-87`); `confirm_cache_evidence()` looks up D0 by that UID (`:245-271`). The D0 parser retains the globally ordered chunks (`:214-242`); test coverage includes the token-budget intermediate continuation (`tests/test_r052_t11_replay.py:118-132`). |
| Subsequent chunks have `cached_tokens=0`; cache + all new tokens equals actual prompt | PASS | The confirmation loop rejects any nonzero continuation cache and requires `first.cached + sum(all new) == prompt_tokens` (`r052_t11_replay.py:259-265`). Scheduler semantics publish cache only on the first chunk and zero it for continuations (`e2base1/python/freetoken/scheduler/prefill.py:409-455`; `core.py:160-164`). D0 preserves `seg_reason` and request rows per completed real segment (`moe/offload_cache.py:437-465, 540-567`), so `token_budget`/`anchor_cap` do not change continuation treatment. |
| Target and follow-up are separate actual requests; raw follow-up is durable before later checks | PASS | Same UID is rejected (`r052_t11_replay.py:250-251`); the owned body writes `followup_raw.json` immediately after the one allowed follow-up and before D0 confirmation/classification (`r052_t11_followup_prepare.py:73-99`). Regression proves raw preservation on later D0 failure (`tests/test_r052_t11_followup_prepare.py:83-103`). |
| Classification has no invented middle rule | PASS | The approved T11 card states `>= floor(full target length, 64)` = H-hook and `<=13376` = H-bug (`plan/01_测试与调研/T11_E1-R003-uid8_缺donate复现记录.md:8-11`). `classify()` implements only those bounds and rejects the open interval (`r052_t11_followup_prepare.py:17-27`; tests `:15-21`). |
| Fresh Linux CPU proof is bound to reviewed files | PASS | Remote report `/data2/FreeToken/runs/dev_R052/cache_evidence_cpu_20261007_130907/report.json` SHA-256 `0d07bdf1db9abcfa5e6b6e8fde6f9d50c73eb9c5495233c837d4a2b7defddb9e` was read back and equals local pointer `R052_CACHE_CPU_LINUX_20261007.json`. It reports `35 passed in 0.13s`, `CUDA_VISIBLE_DEVICES=""`, `torch_loaded=false`, `socket_guard_loaded=true`, `compiled_sources=5`, and matching SHA-256 values for both runners and both tests. |

## First concrete problem

None found in the reviewed CPU repair. The earlier false assumption that an omitted API detail meant failure is removed; an omitted detail is now deliberately unresolved by API and resolved only through D0 admission evidence.

## Gaps and stop condition

- No formal R052 directory/file-dry receipt was performed (`formal_file_dry_performed=false`); no GPU lock, model, service, port, HTTP request, or formal round was used.
- No formal startup review exists for these exact repaired hashes. A future startup review must bind its dry-run receipt and the then-current source hashes before any `--run` path can be considered.
- No R052 measured artifacts exist, so the actual D0/SSE relationship and H-hook/H-bug classification are unproven on GPU. This report is complete for CPU semantic review and deliberately stops here.
