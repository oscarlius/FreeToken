# Independent source review V3

**Verdict: `SOURCE_READY_PDF_UNBUILT`.** The S2 retry1 update is accurately bounded in the Chinese source/rendered HTML and in the English manuscript package. This is not a PDF, submission, product, quality, two-lane, fixed-256, D09/D10, or multi-GPU approval.

## Evidence checked

- The `strata_s2_retry1_update_20261010T013752+0800` archive contains the intended seven preserved files; all seven SHA-256 values match its manifest. Its actual creation time is `2026-10-10T01:37:52.2259564+08:00`. The manifest's internal `T014500` path text is preserved historical content.
- The Chinese `body_v52.html` diff is restricted to C5 and Section 8.2. The rendered v5.2 file makes the corresponding changes. An intercepted, no-write `build_v52.py` execution produced the stored HTML SHA-256 `5c15be2c54a2aa02f92d6c6e20f0b9e7a459acd0fb7f789456080e3f28c7faac` with 11 frozen figures.
- The S2 independent terminal review SHA-256 is `1f83a1666b988aae710980ddb1325b1a6a01082e127147aee5d536a5ac82b6a8`, confirmed locally and by read-only SSH. It records one service, 11 generation calls, `parallel=1`, and `VALID_MEASUREMENT_SUBSET_ONLY`.
- S2 values match the sources: cold decode `77.28/79.16/77.93/74.31`, short decode `78.17/78.02/80.99`; original128 TTFT `0.352402609/1.051615822`, decode `104.86042787492076/102.94564013401457`, actual output `45/60`, and aggregate throughput `64.61892096039446` versus S1 `48.418168677166946`.
- The sources distinguish aggregate output throughput from per-request decode. S1/no-MTP/spec2 and S2/MTP/spec4/spec-min-p0.5 both use `parallel=1`, so the comparison is neither a causal MTP-only result nor true two-lane GPU decoding.
- The fixed-256 payload stopped at EOS after S2 `48/60`, so it is not used as fixed-length acceptance or throughput. Historical `52/60` quality remains historical provenance, not a new v0.1.41/S2 quality result.
- R067d is consistently recorded as raw `failed_harness`, with the original independent `not_met` assessment preserved. It supplies no D09, T16/T17, D12, product, or throughput conclusion.
- `main.tex` has balanced braces, matching detected environments, and 10 citation keys all present in `references.bib`. The English title and body retain multi-GPU as a proposal/derivation and introduce no KTransformers or llama.cpp baseline.

## Remaining limits

Remote read-only verification confirms sealed closure V2 SHA-256 `21cb4de753e1f20ec13d2085e2d4933ea753b2b08e60c200ecff2fb1315cad41`. It did not run a model, GPU, HTTP request, service, compiler, or PDF renderer. `pdflatex` and `bibtex` are unavailable on this workstation PATH; no PDF exists to inspect.
