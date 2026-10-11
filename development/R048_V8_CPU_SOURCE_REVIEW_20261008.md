# R048 v8 CPU/source readiness review — 2026-10-08

## Scope

Read-only review of `r048_t09_v8/r048_t09_prepare_v8.py` and its sealed Linux CPU package. This is not a FILEdry review, startup signature, GPU launch authorization, or T09 acceptance.

## Evidence verified

- Linux stage `/data2/FreeToken/runs/dev_R048/r048_v8_cpu_20261008_064124` is directory mode `0555`; `report.json` is `0444` and SHA-256 `1908342b8d2f026a37d61d9c363c45974eb37d56e7cf50c1345cdce8cb2dbcc0`.
- The report records `50` passed, `CUDA_VISIBLE_DEVICES=''`, socket `connect/connect_ex/listen` denied, and no formal round, lock, or service.
- The source manifest is `0444`, SHA-256 `c027bab9fd1b17ee1b79eff806dc8756efb49aa9560234b3f5ed3f92cbeea338`.
- The actual private reader/checker chain accepted sealed failed metadata for `E2-R049` and `E2-R049a`; the required measured predecessor remains `E2-R049b`, with `formal_predecessor_satisfied=false`.

## Source conclusions

- Admission retains `E2-R040` failed metadata, R050/R051 kept gates, both R049 failures as metadata, and requires `E2-R049b` measured. It does not substitute the failed R049/R049a outcomes.
- `source_hashes()` binds the entry, D07 reader/checker, ordinary startup/client/adapter closure, parser, port allocator, and route helper. FILEdry/startup paths use the v8 schemas and re-check these hashes.
- Performance plans force `98,304` reserve/sequence window and `0.88` memory ratio. Performance removes D0, hybrid trace, and pause; diagnostic is explicitly separate and excluded from performance numbers.
- Ordinary SSE records bind sorted payload wire, candidate frontend IDs, worker IDs, UIDs, SSE output, and exact completion budgets. The two-way workload requires two distinct UIDs and 512 tokens each.
- The all-zero hybrid timing path fails closed because candidate trace bytes contain no explicit no-submit marker; it does not convert a zero row into an all-cache result.

## Result

**CPU/source-ready only.** No issue found in the reviewed closure. R049b must first close measured; then same-entry FILEdry and an independent startup review remain mandatory.
