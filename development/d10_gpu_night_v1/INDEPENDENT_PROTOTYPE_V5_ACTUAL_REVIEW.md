# Independent D10 actual-parent v5 review

Reviewed at `2026-10-09T17:08:52.1437091Z`. This review added only its own artifacts. It ran no GPU, HTTP, service, AIPerf profile, native compilation, or product acceptance.

## Verdict

**PASS_CONDITIONAL_CPU_ONLY — the latest actual v5 packet fixes the prior parser/driver binding failure.** This approves the CPU-bound source, fixture, admission, filedry, and spawn-hook packet. It does not authorize runtime execution.

## Evidence

- The sealed target-host receipt [V5_ACTUAL_V2] has SHA-256 `21e1f9577db18509ce5743a5cecb80b8ed7c993f132524d021dbb288bc0d9f8b`; it and all eight listed sources/fixtures are `0444`, and their remote bytes match the receipt.
- Remote and local `pytest test_d10_aiperf_parse_v5.py test_d10_prototype_owned_parent_v5.py -q` both report **4 passed**. The copied genuine R045 wave1/wave2 raw exports are present on the FT host and retain their source hashes.
- The real v5 entrypoint runs `--filedry` itself. Its emitted plan has four profiles and eight requests: two original and two ignore-EOS commands, each with `--request-count 2`, `--concurrency 2`, and raw exports; it records one-service/8-call budgets and every runtime-scope flag as false.
- `d10_prototype_owned_parent_v5.py` has no old v5-runner/v4-parser hardload. Its retained lifecycle module resolves to `d10_runner_v6` and `d10_parser_v5`. Runner v6 now supplies the parent-required `require_admission`, `argv`, `ORIGINAL`, `INPUT`, `filedry`, and `require_raw_profiles` interface.
- A direct target-host admission check accepted the complete current v5 source set and rejected an otherwise identical set substituting `d10_aiperf_runner_v5.py`. The CPU spawn probe still reports `probe_installed=true` with no GPU or HTTP.

## Remaining gaps

- Exact-256 ignore-EOS raw records do not yet exist; the runtime parser remains fail-closed until it sees exactly two `[256, 256]` records.
- A future root admission must supply native provenance, kept T16 closure, and completed D09 terminal/manifest safe-cleanup records. This CPU review does not require a fabricated D09 PASS.
