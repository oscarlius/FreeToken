# Independent D10 startup review V2

Reviewed at **2026-10-10T00:30:26.848777+08:00**. V2 preserves V1's V3 failure and reviews launcher V5 plus prototype parent V2. It is non-authorizing.

## Verdict

**FAIL — actual D10 computation-path proof is not wired into the prototype.** V5 correctly removes the fictional `E2-D09-GPU=kept` requirement, but prototype V2 cannot establish that `Engine._forward_d10_staggered_decode` runs on the eligible lanes.

## Evidence

- V5 (`0df8d604…4035`) has no aggregate D09 prerequisite. AIPerf V4 (`cf8774a2…0156`) instead requires immutable terminal/manifest paths and hashes, cleanup evidence, and an actual D09 classification. That is sufficient for conditional CPU review; no D09 terminal is needed now.
- The candidate remains clean exact `22ff3a…2032`. The prototype binds default-on source/argv, reused native bytes, one service, and eight AIPerf calls. The remote fake-chain terminal is `c8dc4c31…6ad4`; it only proves injected callbacks and listener rebinding.
- The negative CPU test source covers health pre-exit cleanup and post-stop `OSError(98)` lock retention. Its reported two passed result is not independently executable evidence in this review because no immutable test-output terminal was retained.
- `d10_branch_probe.py` (`b9bcd3f5…59d5`) only defines `install()`. Neither the prototype nor the candidate imports it or calls it. Setting `PYTHONPATH` and `FT_D10_BRANCH_EVENT` does not install the wrapper. A later event file would therefore not prove entry into `_forward_d10_staggered_decode`.

## Required correction

Bind explicit probe installation into the actual service argv/bootstrap, then preserve proof of installation and one entry for each eligible lane with source and service-identity hashes. Retain immutable negative-test evidence. A live prototype also remains separately gated on root admission containing actual D09 terminal/manifest/hash/cleanup records.
