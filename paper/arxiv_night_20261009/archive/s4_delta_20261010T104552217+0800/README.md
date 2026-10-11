# arXiv night draft — 2026-10-09

This directory contains a standalone English author draft for arXiv review. It does not replace `../FreeToken_MultiGPU_CoExec_v5.2.html`, its frozen source, or any sealed measurement artifact.

## Contents

| File | Purpose |
| --- | --- |
| `manuscript.md` | Review-friendly Markdown manuscript. |
| `main.tex` | arXiv-oriented LaTeX source. |
| `references.bib` | Bibliography records. No DOI is asserted. |
| `CITATION_VERIFICATION.md` | Primary-source URL and access-date ledger for every bibliography record. |
| `archive/pre_revision_20261009_2330/` | Byte-preserving copy of the five pre-revision writable files, with hashes in its manifest. |
| `../archive/strata_s2_retry1_update_20261010T013752+0800/` | Byte-preserving copy of the seven files before the S2 retry1 evidence update. The directory name is the recorded creation time; `ARCHIVE_MANIFEST.json` retains its original internal `014500` path strings and hashes. |
| `../archive/strata_s3_parallel2_update_20261010T030225+0800/` | Byte-preserving copy of the seven files before the S3 parallel=2 evidence update, with source hashes and timestamps in `ARCHIVE_MANIFEST.json`. |
| `CLAIM_EVIDENCE_MAP.md` | Claim-by-claim evidence level and source binding. |

## Evidence policy

The manuscript uses these labels throughout:

* **Measured**: a locally sealed or independently reviewed observation.
* **Derived**: a deterministic calculation from stated assumptions and measurements.
* **Proposed**: a design or preregistered experiment with no GPU acceptance result.
* **Pending**: a required result is absent.

R045 supplies a valid four-request FreeToken performance measurement record; all four R045 lanes failed the strict `>30 tok/s` speed gate. D10 group0 supplies separate observational evidence from two requests: both decode speeds were below 30 tok/s, and the original terminal remains `FAILED_HARNESS`. Neither result qualifies D10 for formal development. The historical original R067d remains a reclassified `failed_harness`; its `c17` candidate was CPU-only at that historical point. The separate R067d retry1 is sealed `not_met`: four services and eight valid calls produced equal cache-zero cold 8192+1 A/B outputs under `hybrid_radix`, but token 0 differed from hot (39 versus 248046); D12 was not triggered. Neither R067d record is D09 enabled-mechanism, T16/T17/T03b/T2, D12, throughput, or D10 acceptance. D09 T16 retry1 is separately sealed `kept` with eight services and 100 calls, but only for default-off identity; enabled-path proof remains pending. Strata v0.1.41 S1/S2/S3 are qualifying same-binary, one-service measurement subsets, not accepted two-lane gates. S3's independent review V2 (`050357…df3bb`) and sealed closure V1 (`815798…56477`) bind 11 calls, 42 raw files, and raw manifest `25c258…940bd`; S3 changes only S2 `parallel=1` to `parallel=2`. Its draft layer is loaded but batch-MTP is not opted in (`--batch-mtp` absent and `STRATA_BATCH_MTP` absent), so this is not batch-MTP-in-use evidence. The S2-to-S3 frozen cold/short means fall from 77.17/79.06 to 69.525/71.80 tok/s, a bounded configuration observation rather than a general MTP conclusion. S3 `original128` is 46/60 actual output; aggregate 35.481136 and per-user mean 30.582920 are not per-lane proof. Its diagnostic fixed-256 group also stops at 46/60. Quality 52/60 remains only R001 historical evidence. D10 group0 is recorded as an observational original-profile-only below-threshold result; formal D10 qualification remains pending. V5 was `PARTIAL` / `SOURCE_CORRECTION_REQUIRED_PDF_UNBUILT`; V6 corrected its source blocker. V7 source review passed; V8 requested clarification of this README’s measurement-versus-speed-gate wording. Numbered `INDEPENDENT_SOURCE_REVIEW_V*.json` files retain each review and its source hashes; use the newest review matching the current files. PDF remains unbuilt.

D10 batch155 is a bounded persistent-cache feasibility result: candidate `54955f7` entered the eligible staggered method, completed two requests (46/58), and measured per-request decode 0.8725121807283541/6.967070060487639 tok/s with TTFT 20.316885305/64.321046495 s. Both are below 30, so profile0 is `not_met`; the first valid group stopped and profiles1–3 plus fixed-256 are unrun. Prediction manifest `3216e1551fba79e09a3cd6b0d24f2ac63e991cdab0bed5ea7c60c7c9179ab7b1` gives 33.1–40.0 only as a conditional scenario, not a confidence interval. Both prototypes measured below the threshold (the earlier prototype: 5.855077/1.064367 tok/s), and current measurements cannot distinguish the mechanism from cold-start effects; and the current candidate's new T16 has not been run, so formal GO remains unmet.

## Local build

The intended arXiv sequence is:

```text
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

This workstation did not expose `pdflatex` or `bibtex` on `PATH` when the draft was produced, so a full PDF build is pending an arXiv/TeX environment. The source deliberately uses only standard `article`, `amsmath`, `booktabs`, `geometry`, `hyperref`, and `url` packages plus BibTeX.

## Minimal data required before submission

1. The independent review of this English manuscript and its final rendered PDF.
2. Independent re-check of the already verified primary-source URLs in `CITATION_VERIFICATION.md` at the time of submission.
3. If D09 is reported as enabled: sealed engine commit, enabled-path T16/T17/T03b and the three replay passes, plus per-round prediction residuals. The existing default-off T16 retry1 identity result is not enabled-path proof.
4. To claim D10 qualification or acceptance: prototype binding, terminal T16 result, original and `ignore_eos=true`/256-token results, and per-lane gate verdicts. The bounded group0 observational negative may be reported with its current limitations without implying that this full acceptance set exists.
5. For a causal Strata MTP comparison: retain the S1/S2 same-build records and change only the MTP factor; then obtain fixed-length acceptance where claimed, an independent quality rerun where claimed, and a two-lane protocol where claimed. The current S2 retry1 combined-configuration subset does not supply those results.

