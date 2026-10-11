# D08 / D10 retry2 terminal result

Written 2026-10-11T01:58:25.727136+08:00. User directive revision v3; no push, Ollama remains stopped, paper unchanged.

| Item | Result | Interpretation |
|---|---|---|
| D08 hybrid single | 33.829960 tok/s | 2 unscored SDK warmups completed first |
| D08 hybrid X two lanes | 25.329861 / 25.479408 tok/s | Both ≥19.6: H1 supported; both within prediction19–27 |
| D10 η | failed_harness, no numeric η | Fixed-token graph warmup did not stabilize cache maps; no mechanism verdict or measured bound |
| Fresh first single D0 | 42932 / (255×480) =35.0751634% | bs1/RID0/steps0–254, sole generation |
| Earlier shared X D0 reference | 38.2426471% | Difference3.1674837pp≤5pp: content-dominant guard supported |
| Recovery | 481d3a7 / 98K, SDK pass | df77cb stable15 fields and full argv equal; no rollback |

Actual window 01:35:03–01:55:58, 1255.92s (<2700s). All measured X requests were temperature0, max_tokens256, ignore_eos=false, length256; metric1000/AIPerf ITL(ms). Hybrid used2700slots, auto fetch fraction27.7%; performance D0/trace disabled. Versus user-approved historical X offload references, corresponding lane speed gains48.88% and50.31%; these are historical reference comparisons, not a same-window causal isolation of executor effects. The offload single30.1709957405 reference was reused as instructed.

D0 uses the request-bound ledger. Generic d0_decode.json includes two additional aggregate calls; its35.5851% is not used. η source analysis suggests GDN state advances during repeated raw graph replay despite fixed token; this remains a source-based hypothesis, not a measured diagnosis.

The previous observer was recorded as truncated. Restore07 observer111554 is open until09:00; it has not passed that observation period. Live readback verified exact PID births, production lock, serving/backend_epoch0/restart_attempts0, and Ollama stopped.

Evidence: COMPLETE_WINDOW_EVIDENCE_MANIFEST.json (112 artifacts), RESTORE07_BASELINE_COMPARISON.json, LIVE_RESTORE07_READBACK.json; independent stage addenda under independent_window01_review_20261011T014749+08_00. D05/D09 CPU repairs have their own candidates and acceptance evidence; this GPU window does not accept either repair or authorize their T16.
