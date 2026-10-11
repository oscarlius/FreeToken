# Independent source review V4 — S3 update

## Verdict

PASS — `SOURCE_READY_PDF_UNBUILT`. The S3 source update is traceable and reproducible as source. It has not received rendered-PDF review, source full-acceptance, product acceptance, or performance acceptance.

## Evidence

- `paper/archive/strata_s3_parallel2_update_20261010T030225+0800/ARCHIVE_MANIFEST.json` — archive creation time is `2026-10-10T03:02:25.6090187+08:00`; its SHA-256 is `4fa2e12b88e1de540acd179aa85a9f28013eb9ad1a6c30bbbac742a668d294af`. All seven archived files match both their recorded byte counts and SHA-256 values.
- `paper/src/body_v52.html` against the archived `body_v52.html` — the only source hunks are C5 and §8.2: S1/S2 becomes S1/S2/S3 and four S3 evidence lines are added. The subtitle retaining “多卡部分未实测” is identical before and after.
- `paper/src/build_v52.py` re-executed in memory with bytecode writes disabled — substituted all 11 registered figures and reproduced SHA-256 `5b18ccf3f1e0f78bfab2678e88dbb0880a7fa1c6cef737a68f291ba4ac6cd151` for `FreeToken_MultiGPU_CoExec_v5.2.html`, without overwriting that artifact.
- `strata/development/r002_v0141_s3_parallel2_v2_20261010/S3_PARALLEL2_ACTUAL_TERMINAL_INDEPENDENT_REVIEW_V2.json` — current SHA-256 equals `050357014e41bb176f3fcd2b6d85767f4f9340733f8e73165bc361df434df3bb`; it binds the one-service, 11-call `VALID_MEASUREMENT_SUBSET_ONLY` S3 record.
- `development/night_execution_20261009/STRATA_S3_SEALED_CLOSURE_V1.json` — current SHA-256 equals `815798883d179b42f2777dab08ce16d7962a8e41ae5863eebd810096c7556477`; it binds 42 raw files and manifest `25c25830234a2a7c1a28fc5a4f99deae985c4e4bb27664f601534eac3e9940bd`.
- `paper/arxiv_night_20261009/{main.tex,manuscript.md,CLAIM_EVIDENCE_MAP.md}` — all hold the S3 review/closure hashes and performance boundaries; the evidence map also retains D09 as default-off identity-only and D10 as prototype-pending. Their terms agree that draft loaded is not batch-MTP opt-in, aggregate/per-user statistics do not prove both lanes exceed 30 tok/s, fixed-256 is unsupported, and 52/60 was not rerun.
- `main.tex` static checks — unescaped braces are balanced (163/163), every cited BibTeX key resolves, and no unreferenced bibliography key exists.

## Gaps

- `arxiv_night_20261009` has zero PDF files; `pdflatex` and `bibtex` are absent from `PATH`. No final PDF was compiled, rendered, or independently reviewed.

## Risks

- This review does not establish a full PDF submission artifact or any broader runtime result. S3 remains a bounded measurement subset: it cannot establish product, quality, two-lane, multi-GPU, enabled-D09, or D10 acceptance.
