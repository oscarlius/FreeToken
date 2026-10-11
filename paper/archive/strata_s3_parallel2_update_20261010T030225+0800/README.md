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
| `CLAIM_EVIDENCE_MAP.md` | Claim-by-claim evidence level and source binding. |

## Evidence policy

The manuscript uses these labels throughout:

* **Measured**: a locally sealed or independently reviewed observation.
* **Derived**: a deterministic calculation from stated assumptions and measurements.
* **Proposed**: a design or preregistered experiment with no GPU acceptance result.
* **Pending**: a required result is absent.

Only the four-request R045 decode experiment is newly reported as a FreeToken performance measurement. It is a negative result: all four lanes were below the strict `>30 tok/s` target. The formal R067d GPU harness is also recorded, but as `failed_harness` with an independent semantic `not_met` assessment: it supplies no D09 measurement or T16/T17/D12 acceptance. Strata v0.1.41 S1/S2 are separately reported as same-binary, one-service measurement subsets. The valid S2 retry1 record has 11 generation calls and a 40-file raw manifest, but it is not product, quality, fixed-256, or two-lane acceptance. Client concurrency two queues one engine lane; S1/spec2/no-MTP and S2/MTP/spec4/min-p0.5 differ in more than MTP, so no causal MTP-only effect is reported. Both fixed-256 subloads stop early (S1 45/60, S2 48/60). Thus no two-lane or multi-GPU performance, D09, or D10 result is reported. The `c17` candidate is CPU-only and is not GPU evidence.

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
3. If D09 is reported: sealed engine commit, T16/T17/T03b and the three replay passes, plus per-round prediction residuals.
4. If D10 is reported: prototype binding, T16 result, original and `ignore_eos=true`/256-token results, and per-lane gate verdicts.
5. For a causal Strata MTP comparison: retain the S1/S2 same-build records and change only the MTP factor; then obtain fixed-length acceptance where claimed, an independent quality rerun where claimed, and a two-lane protocol where claimed. The current S2 retry1 combined-configuration subset does not supply those results.
