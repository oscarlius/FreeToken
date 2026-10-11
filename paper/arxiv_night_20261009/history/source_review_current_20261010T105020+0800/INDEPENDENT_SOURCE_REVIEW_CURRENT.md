# Independent Source Review - 2026-10-10T10:32:19.416025+08:00

**Verdict: PASS_SOURCE_PDF_UNBUILT.**

The four-English-source T16 delta is accurate. Each active D10 location now states that the current candidate new T16 has not been run, matching the abstract/limitations, revision log, Chinese source, and generated HTML. The pre-edit four-file archive at freetoken/paper/arxiv_night_20261009/history/t16_wording_20261010T103040+0800 hashes to the former reviewed bytes; no protocol or result changed.

D10 batch155 remains accurately bounded: candidate 54955f7, outputs 46/58, TTFT 20.316885305/64.321046495 s, decode 0.8725121807283541/6.967070060487639 tok/s, profile0 not_met, and profiles1-3 plus ignore_eos/fixed-256 unrun. Both prototype variants are below threshold; the current measurements cannot distinguish mechanism from cold-start effects and establish no cache-reset implementation-defect cause.

R067 historical failed_harness and retry2/batch154 FAILED_HARNESS remain preserved. C5 remains S1/S2/S3 only: no S4, retry1-S4, 1733267, or 497.319 measurement entered the seven reviewed sources. Multi-GPU remains derived/proposed. PDF remains unbuilt.
