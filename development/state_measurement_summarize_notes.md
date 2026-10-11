# State measurement summarizer

`state_measurement_summarize.py` is a read-only post-measurement reader for the assigned T04p1, T10p1, and T11p2 round directories. It requires the state runner's exact terminal `status_batchN.json`, `live_checks.json`, `admission.json`, original trace path and SHA, per-arm evidence, and card-specific artifacts. Every replay is joined to the original trace's full `messages_sha` set. It creates two new JSON files only: a reviewer-oriented summary and initial `ft_round/v2` metadata with `pending_review`, no proposed verdict, and empty history.

The admitted remote `agent_trace.py` stores the first 16 hexadecimal characters of its canonical messages SHA-256. Replay `round` is the source trace-list index, while a reverse trace's `record.round` remains its original round number. The reader validates both mappings; it does not accept a substituted full-length digest or a self-consistent replay with the wrong trace index.

T10 lazily loads the existing server tokenizer at `/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay` for exact full-text token positions; `--tokenizer-path` can point to that admitted tokenizer explicitly. T04/T11 and `--self-test` remain stdlib-only and do not import Transformers, access a round, or write output.

T10 also requires the three archived root-level `cmp_cold_B1_B2`, `cmp_cold_B1_B3`, and `cmp_cold_B2_B3` JSON/log pairs. Their original JSON payloads and hashes remain diagnostics; only log return codes 0 and 1 are accepted.

The tool preserves state-equivalence and D3 evidence as diagnostics. It reports missing UID-to-log mappings or historical evidence as gaps; it does not diagnose D03/D04 or publish a verdict.
