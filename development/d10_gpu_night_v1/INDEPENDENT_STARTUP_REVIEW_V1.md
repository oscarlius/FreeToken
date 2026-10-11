# Independent D10 startup review V1

Reviewed at **2026-10-10T00:26:23.764195+08:00**. This is a read-only, non-authorizing review of `d10_owned_launch_v3.py` (`1a3aa0e5…d435`), `d10_t16_full_runner_v2.py` (`c839f101…244a`), and `d10_aiperf_runner_v3.py` (`89f79804…6a58`).

## Verdict

**FAIL — V3 must not admit a D10 startup.** Static source and native-byte binding are sound enough for review, but V3 requires the fictional aggregate `E2-D09-GPU=kept`. The canonical round root `/data2/_shared/runs/ft_rounds` contains only `.dryrun_E2-D09-T16-night-20261009_2bt6j00i` for D09 and no `E2-D09-GPU/round.json`, terminal, manifest, hash binding, or closed-round pin. An independent round can proceed after `not_met`; it cannot be rewritten as an aggregate `kept` prerequisite.

## Evidence

- Candidate source is exact `22ff3a389eae3724cdca9a45f2e19577082a2032`, clean, with merge-base `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`. It is a detached HEAD, so no source-branch proof exists.
- Native provenance `d10_native_provenance_v2.json` (`7c7aaaec…4982`) binds default-off `--d10-staggered-decode` / `d10_staggered_decode`, candidate `args.py` `203c7c85…1a57`, and identical reused extension hashes. Root reuse receipt is `de2f510f…44b3`; it records no compilation and no GPU validation.
- CPU FILEdry terminal `751cd372…2e36` records 8 arms, 96 simulated calls, all listener rebinds, and zero GPU/service/HTTP/lock/formal-round use. Its atomic receipt is `383d2bec…0cda`. This only proves the fake CPU path and includes the same hard-coded `required_d09_terminal=kept` predicate.
- AIPerf V3 plans four profiles × two calls with concurrency two: eight calls, one service maximum. Its `--run` admission also accepts only `d09_gpu_terminal=kept`, without immutable terminal or manifest hashes.

## Required correction

Bind real completed D09 terminal records in both V3 admission surfaces: terminal and manifest locations, their SHA256 values, verdict, and safe-owned-cleanup evidence. Seal the policy that determines whether each actual terminal classification (`kept`, `not_met`, or `failed_harness`) can advance. Then obtain a completed prototype-T16 terminal and independent review before running AIPerf.

No D10 startup, service, GPU allocation, HTTP request, or AIPerf `--run` is authorized by this review.
