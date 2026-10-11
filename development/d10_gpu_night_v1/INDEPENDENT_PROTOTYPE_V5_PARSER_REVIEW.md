# Independent D10 parser v5 review

Reviewed at `2026-10-09T17:05:03.5276084Z`. This review added only its own artifacts and ran no GPU, HTTP, service, native compile, AIPerf profile, or product acceptance.

## Verdict

**FAIL — parser v5 is locally correct on genuine R045 raw records, but it is absent from both the target-host fixture packet and the actual D10 runtime path.**

## Evidence

- Local `test_d10_aiperf_parse_v5.py` passed **2 tests**. Direct parsing of the genuine non-flat R045 retry1 exports yielded wave1 and wave2 counts `[46, 58]`, with actual request IDs, positive TTFT, and positive output-token throughput. Fixture SHA-256 values are `d251c48d…edb86` and `67655667…ae50`.
- Parser v5 correctly reads `metadata.x_request_id`, `metrics.usage_completion_tokens.value`, `metrics.output_token_count.value`, `metrics.time_to_first_token.value`, and `metrics.output_token_throughput_per_user.value`. This repairs the prior flat-record defect.
- `LINUX_CPU_SPAWN_RECEIPT_V5_PARSER.json` has the specified SHA-256 `610c096a2325bb3a9067289c2feced074ce941a53e56a944ab38bd60086d6aa3`; it and its four listed source files are remote mode `0444`, and their source hashes match.

## Blocking gaps

- The target FT host lacks `/data2/FreeToken/development/r045_production_aiperf_20261009/raw_retry1/wave1` and `wave2`. An independent remote parser test therefore failed **1 passed, 1 failed** because it found zero raw records.
- The new CPU receipt only reruns `d10_branch_startup_v4.py --cpu-spawn-probe`; it does not execute the parser test or prove the R045 fixture exists. Its source hash list also omits both raw fixture hashes.
- The actual parent remains on the old path: `d10_prototype_owned_parent_v4.py` loads `d10_aiperf_runner_v5.py` and `d10_aiperf_parse_v4.py`, then pins their old hashes in admission. No future D10 profile can reach v5 through this parent.
- `d10_aiperf_runner_v6.py` cannot simply replace the old runner. The parent requires `require_admission`, `argv`, `ORIGINAL`, and `INPUT`; v6 supplies none of them.

## Required repair

Author/root must integrate v5 parsing into a runner that preserves the old frozen argv/admission interface, update the actual parent and sealed admission hash list, and provide the immutable R045 raw fixture packet on the FT host. A new `0444` CPU receipt must execute the parser test and bind both fixture hashes. Request another independent review after that packet exists.
