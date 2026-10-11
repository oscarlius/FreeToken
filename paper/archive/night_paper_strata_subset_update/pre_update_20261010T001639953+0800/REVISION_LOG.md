# Revision log

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
