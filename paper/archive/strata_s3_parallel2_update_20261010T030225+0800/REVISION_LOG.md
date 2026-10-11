# Revision log

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
