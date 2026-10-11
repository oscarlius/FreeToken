# arXiv night draft — 2026-10-09

This directory contains a standalone English author draft for arXiv review. It does not replace `../FreeToken_MultiGPU_CoExec_v5.2.html`, its frozen source, or any sealed measurement artifact.

## Contents

| File | Purpose |
| --- | --- |
| `manuscript.md` | Review-friendly Markdown manuscript. |
| `main.tex` | arXiv-oriented LaTeX source. |
| `references.bib` | Bibliography records. No DOI is invented; records marked `VERIFY BEFORE SUBMISSION` need bibliographic confirmation. |
| `CLAIM_EVIDENCE_MAP.md` | Claim-by-claim evidence level and source binding. |

## Evidence policy

The manuscript uses these labels throughout:

* **Measured**: a locally sealed or independently reviewed observation.
* **Derived**: a deterministic calculation from stated assumptions and measurements.
* **Proposed**: a design or preregistered experiment with no GPU acceptance result.
* **Pending**: a required result is absent.

Only the four-request R045 decode experiment is newly reported as a measurement. It is a negative result: all four lanes were below the strict `>30 tok/s` target. Multi-GPU performance, D09, D10, and the v0.1.41 Strata S1/S2 comparison are not reported as completed experiments.

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
2. Bibliographic verification for all records marked `VERIFY BEFORE SUBMISSION` in `references.bib`.
3. If D09 is reported: sealed engine commit, T16/T17/T03b and the three replay passes, plus per-round prediction residuals.
4. If D10 is reported: prototype binding, T16 result, original and `ignore_eos=true`/256-token results, and per-lane gate verdicts.
5. If a Strata result is reported: v0.1.41 build receipt, S1 argv/stderr proof of no MTP/draft layer, and S1/S2 workload records. Otherwise retain it as pending.

