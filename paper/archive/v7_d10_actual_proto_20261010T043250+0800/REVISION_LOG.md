# Revision log

## 2026-10-10T03:43:10+08:00 — English V6 R067d Markdown source correction

- Preserved the seven English source files and the V5 independent-review JSON in `../archive/english_v6_r067d_markdown_correction_20261010T034310+0800/`, named from the actual archive creation time `2026-10-10T03:43:10.8201817+08:00`. The archive preserves V5 review SHA-256 `c3ef934df49619b46856e9e2f3d588e07eda40979fdb35c07b8e43db22eac445` and `reviewed_at_utc` `2026-10-09T19:07:47.5605959Z`; its PARTIAL / `SOURCE_CORRECTION_REQUIRED_PDF_UNBUILT` verdict is not altered.
- Corrected only the Markdown conclusion that V5 identified: the original R067d remains reclassified `failed_harness`, while retry1 is sealed `not_met` with D12 not triggered; neither promotes D09 enabled behavior, D10, T16/T17/T03b/T2, D12, or causal Strata MTP acceptance. README now records this V5→V6 correction boundary.
- No Chinese source or generated HTML was edited. No GPU, remote command, compile, model service, HTTP generation, push, submission, or PDF build occurred. A new independent review is required.

## 2026-10-10T03:39:41+08:00 — English V5 D09 retry1 freshness correction

- Preserved seven English source files before editing in `../archive/english_v5_d09retry1_freshness_20261010T033941+0800/`, named from the actual archive creation time `2026-10-10T03:39:41.6462330+08:00`. `ARCHIVE_MANIFEST.json` records source bytes, timestamps, and SHA-256 values.
- Corrected the stale original-R067d-only account. The original `failed_harness` and its historically CPU-only `c17` candidate remain historical. The separate retry1 is a sealed `not_met` round: formal manifest `928bfbbd7fc30f2134c4e5ece5cc5e3d2ac05f2fa6c779a3f604e9090494f12e`, raw manifest `e2e3cf442b0a467a241b10d530920a12cc95893dd371255420f9af7e15bc7fb6`, independent review `12d812dd109023bb3201ec6b0969a81cd3d9802186d8466168f06794ff6b76e9`; four services and eight calls completed. The cache-zero cold 8192+1 A/B outputs agree but differ from hot at token 0 (39 versus 248046), the configured product stop; D12 was not triggered.
- Bound D09 T16 retry1’s default-off-only `kept` result: eight services, 100 calls, and formal manifest `0bf2dfd9a4b677875f8a9c9a2c876a07fee3c33555f618635d10e9c746b97de0`. It does not prove D09 enabled behavior, T17, T03b, or T2. D10 remains in T16 GPU work with no prototype measurement; its prediction is unchanged.
- Reworded S1/S2/S3 as qualifying same-binary measurement subsets, retaining their actual scope while stating that no accepted two-lane gate, causal MTP-only estimate, quality rerun, or fixed-256 acceptance exists.
- English-source-only pass: Chinese v5.2 source and generated HTML were not edited, and no GPU, remote command, compile, model service, HTTP generation, push, submission, or PDF build occurred. This revision requires a new independent English source review.

## 2026-10-10T03:02:25+08:00 — Strata S3 parallel=2 measurement-subset update

- Preserved the seven writable target files before editing in `../archive/strata_s3_parallel2_update_20261010T030225+0800/`, named from the actual archive creation time `2026-10-10T03:02:25.6090187+08:00`. Its `ARCHIVE_MANIFEST.json` records source bytes, timestamps, and SHA-256 values; it does not alter the historical S2 archive or manifest.
- Added S3 V2 independent review SHA-256 `050357014e41bb176f3fcd2b6d85767f4f9340733f8e73165bc361df434df3bb` and sealed closure V1 SHA-256 `815798883d179b42f2777dab08ce16d7962a8e41ae5863eebd810096c7556477`: one service, 11 calls, 42 raw files, and raw manifest SHA-256 `25c25830234a2a7c1a28fc5a4f99deae985c4e4bb27664f601534eac3e9940bd`.
- Recorded the sole S2→S3 configuration delta, `parallel=1` to `parallel=2`, under the same `fb58e0d` binary `a1f4bc…aa7a0`. S3 loads the draft layer (`b3e023…ae497`) but has neither `--batch-mtp` nor `STRATA_BATCH_MTP`; following frozen upstream `docs/BATCHING.md`, it is not reported as batch-MTP in use.
- Kept every boundary: S2→S3 cold/short frozen-workload means decline 77.17/79.06 to 69.525/71.80 tok/s; this is not a general MTP conclusion. S3 `original128` per-request output is 20.608912/40.556927 tok/s, while aggregate 35.481136 and per-user mean 30.582920 are not per-lane proof. `ignore_eos=true,max_tokens=256` still stops at 46/60 and is diagnostic only. Quality 52/60 remains historical R001-only evidence. The preserved `load_v2` cleanup error is cured by exact-owner recovery `83f7…fea0`, not a product `not_met` result.
- Updated only v5.2 C5 and §8 plus the corresponding English source/evidence records, then regenerated `../FreeToken_MultiGPU_CoExec_v5.2.html` locally. No GPU, model service, HTTP generation, remote compilation, installation, upload, push, arXiv submission, or PDF build occurred. The source-ready PDF remains unbuilt and requires independent review after this revision.

## 2026-10-10T01:37:52+08:00 — Strata S2 retry1 measurement-subset update

- Preserved all seven writable target files before editing in `../archive/strata_s2_retry1_update_20261010T013752+0800/`, named from the recorded archive creation time `2026-10-10T01:37:52.2259564+08:00`. `ARCHIVE_MANIFEST.json` is SHA-256 `632b91d8af518602ef5e0b96664b42ee15c60cb6c7d0804edb8ff15e2dd34264` and records source bytes, original source timestamps, and SHA-256 values. Its internal `archive` path strings retain the original `014500` label because the manifest is byte-preserved.
- Replaced the stale S2 `failed_harness` wording with the independently reviewed retry1 result: `VALID_MEASUREMENT_SUBSET_ONLY`, one service, 11 generation calls, and 40-file raw manifest SHA-256 `6eb616c55d050651951f154c5c35f277c01e31c756e61c17aa23980b78b50850`. The review is SHA-256 `1f83a1666b988aae710980ddb1325b1a6a01082e127147aee5d536a5ac82b6a8`.
- Bound the actual MTP slice SHA-256 `efeaa60a06b7f5608b8959ab2bd6bf626f4f152c234b999cd0f6f6304b6257ec`, the preserved S1 non-MTP slice SHA-256 `fc9f9cce45c58308d583dfa5d07509b7d5822dbc9795b9e74f6f6a1cfe9e37cf`, and root sealed closure V2 SHA-256 `21cb4de753e1f20ec13d2085e2d4933ea753b2b08e60c200ecff2fb1315cad41`. Closure V2 corrects a readback caller file-versus-directory mismatch only; it changes no raw measurement byte or verdict.
- Kept the boundaries explicit: `parallel=1`; client concurrency two queues one engine lane; S1/spec2/no-MTP versus S2/MTP/spec4/min-p0.5 is not a causal MTP-only comparison; fixed-256 is unsupported (S1 45/60 and S2 48/60); the 52/60 quality observation was not rerun; no product, quality, two-lane, multi-GPU, D09, or D10 acceptance is claimed.
- Updated only the v5.2 C5 row and §8 source, then regenerated `../FreeToken_MultiGPU_CoExec_v5.2.html` locally. No GPU, model service, HTTP generation, remote compilation, installation, upload, or submission occurred. PDF remains unbuilt.

## 2026-10-10 — Strata subset update

- Preserved the seven writable target files before this update in `../archive/night_paper_strata_subset_update/pre_update_20261010T001639953+0800/`; its generated `ARCHIVE_MANIFEST.json` records source bytes, SHA-256 values, and filesystem creation times.
- Updated only the v5.2 C5 contribution row and §8, then regenerated `../FreeToken_MultiGPU_CoExec_v5.2.html` from `src/build_v52.py`.
- Recorded Independent Result Review V3 SHA-256 `9a3f29e877a1ad2fd462f867db514fcc48c8506237ff52a64fa3971c81392c58`: Strata S1 is a `PARTIAL` no-MTP measurement subset; the fixed-256 `ignore_eos` subload is `not_met`; S2 made zero generation calls because the harness read the outer log. V3 corrects V2's midnight timestamp placeholder and preserves V2 bytes and findings.
- Preserved the source-ready, PDF-unbuilt state. No GPU, model service, HTTP generation, remote compilation, installation, upload, or submission occurred.

## 2026-10-09T23:33:39+08:00

- Read the independent full review; its submission block remains in force.
- Preserved the five pre-revision writable files in `archive/pre_revision_20261009_2330/` before editing; see `ARCHIVE_MANIFEST.md` for SHA-256 values.
- Added the sealed D09 v4 prediction SHA-256 to the evidence map and retained its prediction-only status.
- Recorded R067d as raw `failed_harness` and independent semantic `not_met`: three services, seven generation calls, six hot completions, no cold A/B cell, completed cleanup, and unmet D12 conditions. It is not GPU performance or acceptance evidence.
- Expanded `main.tex` from a compressed synopsis into a full article aligned with the Markdown manuscript.
- Replaced all nine `VERIFY BEFORE SUBMISSION` placeholders with checked primary-source metadata and added `CITATION_VERIFICATION.md`.
- Did not compile TeX: this workstation has no `pdflatex` or `bibtex` on `PATH`; no tool was installed and no remote, CPU recompilation, GPU, model service, or HTTP model endpoint was used.

## 2026-10-09T23:34:09+08:00

- Re-read the primary arXiv records for FlexGen and Layered Prefill and corrected the complete FlexGen author list and the Layered Prefill title from ``LLM Serving'' to its verified ``MoE Serving'' title.

## 2026-10-09T23:34:32+08:00

- Static self-check passed: 10/10 cited keys resolve, no unused entry, no `VERIFY BEFORE SUBMISSION` marker, nested TeX environments are valid, and TeX/BibTeX brace balances are zero.
- PDF rendering remains unverified because `pdflatex` and `bibtex` are unavailable on `PATH`; no build or installation was attempted.

## 2026-10-09T23:34:46+08:00

- Removed unverified publication-year fields from the three documentation records and the Strata repository record; their access dates remain in the bibliography notes and citation ledger.

## 2026-10-09T23:35:06+08:00

- Re-ran the source check after the bibliography correction: 10/10 cited keys resolve, no unused entries or verification placeholders remain, TeX and BibTeX brace balances are zero, and TeX environment nesting is valid.

## 2026-10-09T23:46:47+08:00

- Closed the independent review's low-severity Markdown seal omission by adding the same D09 prediction payload SHA already bound in TeX and the evidence map. No technical claim or measurement status changed.

2026-10-10T00:24:06.521754+08:00 Root corrected main.tex limitations after independent Strata subset review V1: limited S1 no-MTP evidence, fixed256 not achieved, no matched S2 delta. main.tex SHA256 90cfe5a606a7c53498550d88b20f7bae91aef2d36676c9455d40c222cfe3f662.

2026-10-10T00:44:43.288719+08:00 R067d wording updated to user 00:35 append-only failed_harness reclassification; original independent not_met retained as historical assessment; no product conclusion. Archive freetoken\paper\arxiv_night_20261009\archive\r067_reclassification_20261010T004443+0800.
