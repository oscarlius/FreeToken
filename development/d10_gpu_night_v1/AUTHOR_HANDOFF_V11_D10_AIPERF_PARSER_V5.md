# D10 AIPerf parser v5 handoff

The v5 parser reads only retained AIPerf 0.11 `profile_export.jsonl` records.
It extracts `metadata.x_request_id`, `metrics.usage_completion_tokens.value`,
`metrics.output_token_count.value`, `metrics.time_to_first_token.value`, and
`metrics.output_token_throughput_per_user.value`; completion/output mismatch
or duplicate IDs fail closed.

The retained R045 retry1 wave1/wave2 exports are genuine raw fixtures and
prove request IDs, TTFT, decode rate, and strict original counts of 46 and 58
(both greater than 30).  No retained AIPerf raw export with exact 256 outputs
exists in this workspace.  The v5 test therefore proves that the same genuine
schema is rejected by the ignore-EOS predicate, rather than manufacturing a
flat or synthetic 256 record.  A future runtime can pass only with two raw
records in profile order `[256, 256]`.

`d10_aiperf_runner_v6.py` binds the v5 parser digest for a future admission.
This source-only correction does not start GPU, HTTP, AIPerf, service, or
native compilation and awaits independent reviewer re-check.
