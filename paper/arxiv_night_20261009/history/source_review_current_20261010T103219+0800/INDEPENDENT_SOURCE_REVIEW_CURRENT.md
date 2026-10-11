# Independent Source Review - 2026-10-10T10:29:09.901839+08:00

**Verdict: SOURCE_CORRECTION_REQUIRED_PDF_UNBUILT.**

The seven current source hashes are bound in the companion JSON. The prior current review was byte-preservingly archived to freetoken/paper/arxiv_night_20261009/history/source_review_current_20261010T102909+0800 before this record was written.

D10 batch155 facts agree across the active sources: candidate 54955f7; 46/58 outputs; TTFT 20.316885305/64.321046495 s; decode 0.8725121807283541/6.967070060487639 tok/s; profile0 not_met; later profiles and fixed-256 unrun. The sources correctly state that both prototype variants were below threshold, current measurements cannot distinguish mechanism from cold-start effects, and no cache-reset implementation defect is established as the cause. The old R067 failed_harness and retry2/batch154 FAILED_HARNESS records remain preserved.

**Required source correction:** manuscript.md:112, main.tex:125, README.md:29, and CLAIM_EVIDENCE_MAP.md:13 use no-passing, has-not-passed, or absent-pass wording for the candidate T16. That wording is weaker than the required fact, the current candidate new T16 has not been run, and conflicts with the same sources' abstracts/limitations and both Chinese HTML sources. Replace only those active phrases with the exact unrun status, then rerun source review.

C5 remains S1/S2/S3 only. No S4, retry1-S4, driver 1733267, or 497.319 measurement appears in the reviewed sources; HTML s4 matches are the cost-model section id. Multi-GPU claims remain derived/proposed, with no target multi-GPU measurement. PDF remains unbuilt.
