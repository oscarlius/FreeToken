# Independent Strata subset review V1

Review time: `2026-10-10T00:22:41.309129+08:00`, read-only. The reviewed Strata record is [INDEPENDENT_RESULT_REVIEW_V3.json](../../../strata/development/r002_v0141_night_execution_20261009/INDEPENDENT_RESULT_REVIEW_V3.json), SHA-256 `9a3f29e877a1ad2fd462f867db514fcc48c8506237ff52a64fa3971c81392c58`.

## Verdict

**PARTIAL.** The added C5/§8 material accurately presents the V3-bounded S1 result and its exclusions. The English TeX source remains internally inconsistent, so the paper is not release-ready. No PDF was built or rendered.

## Verified content

- The v5.2 assembled HTML and `src/body_v52.html` each changed only the C5 row and §8 material (9 added / 2 deleted lines against the supplied pre-update archive).
- S1 is correctly limited to one service, 11 reserved calls, no MTP, and no product acceptance. Its seven preserved cold probes match raw values: 32,064/128 TTFT `8.385, 7.997, 8.028, 8.045` s and decode `61.40, 63.05, 63.26, 63.35` tok/s; 2,012/512 TTFT `1.562` s and decode `66.31, 64.49, 60.44` tok/s.
- `original128` correctly reports 46/60 actual outputs and the stated per-user TTFT/decode values. `ignore_eos=true,max_tokens=256` correctly remains `not_met`: both raw HTTP-200 SSE streams stop at 45/60 tokens.
- The new text correctly says client concurrency 2 queues on one engine lane because S1 has no `parallel` key and passed no `--batch`; it does not claim two GPU decode lanes.
- S2 is correctly limited to a harness failure before generation (`generation_calls_reserved=0`), therefore no MTP delta or product/performance failure. The 52/60 historical observation is correctly treated as confounded provenance only.

## Blocking inconsistency

`main.tex:204-210` now reports the valid S1 no-MTP subset, while unchanged `main.tex:216` says: “Strata has no no-MTP result in this paper.” Both cannot be true. The missing comparison is S1-versus-S2 MTP, not the S1 subset itself.

## PDF

`freetoken/paper/FreeToken_MultiGPU_CoExec_v5.2.pdf` does not exist, and no PDF exists under `arxiv_night_20261009`. This review did not run a PDF build or rendering check.
