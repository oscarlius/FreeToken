# T09 v8 and T05 v16 CPU handoff

Root completed both new private source packages. The Linux CPU runs used `CUDA_VISIBLE_DEVICES=''` and denied socket connect/connect_ex/listen. These are CPU source checks; neither package has formal FILEdry, an R startup signature, a GPU run, or acceptance.

## T09 / E2-R048 v8

Entry: `development/r048_t09_v8/r048_t09_prepare_v8.py`. Candidate remains `8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`; parent remains `effb9969706922ddad9e59b96377e46469ebe97f`. Arms, 98,304/0.88 configuration, request lengths, native timing criteria, and production/diagnostic separation are unchanged.

The measured prerequisite is now **E2-R049b**, because R049a closed as failed_harness. Both R049 and R049a are retained as failed metadata. The private D07 reader accepts canonical `round_json_sha256` and legacy `round_sha256`, rejects conflicting/missing/invalid values, and runs only the fixed-SHA readonly same-directory canonical checker for these exact T21 predecessors. R040/R050/R051 checks remain in force. FILEdry and startup paths/schemas are new, so an old signature cannot admit v8.

- Windows: 38 PASS / 12 Linux-only checks skipped.
- Linux: **50 PASS**.
- Stage: `/data2/FreeToken/runs/dev_R048/r048_v8_cpu_20261008_064124` (0555, files 0444).
- Report SHA: `1908342b8d2f026a37d61d9c363c45974eb37d56e7cf50c1345cdce8cb2dbcc0`.
- Source MANIFEST SHA: `c027bab9fd1b17ee1b79eff806dc8756efb49aa9560234b3f5ed3f92cbeea338`.
- Pytest log SHA: `6f3ec955a564397d1a774518f46b388b653bc47b4ec603316ba56939879d7c02`.
- Actual R049 and R049a pin → reader → D04 history checker: PASS. No prior raw payload was read.

The first Linux CPU stage (`r048_v8_cpu_20261008_064100`) remains readonly with its FAIL report. Its new fixture attempted to create a manifest after the actual canonical writer had already sealed the fixture directory. The replacement fixture restores write permission only in its own temporary directory while creating fixture metadata, then seals it before the reader runs. No formal round, model, or GPU was involved.

Next: actual R049b D04 measured → same-entry real-path FILEdry → independent R startup review → queued GPU run. R049b has not yet run.

## T05 / E2-R045 v16

Entry: `development/r045_section14_draft_v16/source/r045_d06_t05_prepare.py`. Candidate remains `effb9969706922ddad9e59b96377e46469ebe97f`; original T05 a–e plus D06 G3/G4 scope and 98,304/0.88 remain unchanged. Speed arms retain the production configuration; H1/timeline/pause evidence remains separate.

The measured prerequisite is now **E2-R040f**, because R040e closed as failed_harness. A private D07/checker copy adds the same canonical/legacy SHA compatibility and exact readonly checker binding for R040a/R040c/R040d/R055b failed metadata and the future R040f measured prerequisite. It does not edit any old pin, round, source package, or verdict. Source identities, FILEdry and startup schemas use v16 and include the checker.

- Windows: 74 PASS / 12 Linux-only checks skipped.
- Linux: **86 PASS**, including the original 73 checks and actual reader/checker contract cases.
- Stage: `/data2/FreeToken/runs/dev_T05/r045_section14_v16_cpu_20261008_064400` (0555, files 0444).
- Report SHA: `b7c97773a79b43909f6e7b6f223d913920b95f6332b11fd8e33ba1e7a05034ef`.
- Source MANIFEST SHA: `049ea8bd59138321ac85f1c3c335db0e9ae4dee3ea99132c8ef68580ac01171f`.
- Pytest log SHA: `a2de65ac092b566662b8bb4f297b27a306ad76b07945412870c557d39de73d74`.
- Actual R040a/R040c/R040d/R055b/R040/R041 metadata pin → reader → history checks: **6/6 PASS**, without reading prior raw payloads.

Next: actual R040f D04 measured → same-entry real-path FILEdry → independent R startup review → queued GPU run. The future measured round in CPU contract tests is only a `/tmp` fixture; no formal R040f result has been created.

## Independent R CPU/source review

R reviewed both sealed source packages and actual CPU reports. The scope remains **CPU/source-ready only**; it grants no FILEdry/startup/GPU authority.

- T09: [R048 v8 CPU source review](R048_V8_CPU_SOURCE_REVIEW_20261008.md), SHA `dd09839971fd38cedea0b8be87fbeabeeb06697e3dcacbf6db6297044e4816c8`.
- T05: [R045 v16 CPU source review](R045_V16_CPU_SOURCE_REVIEW_20261008.md), SHA `44ac40c5732acf7530ba3b2ff42cae69b0e59dc4b57d11791947171593e181ae`.
