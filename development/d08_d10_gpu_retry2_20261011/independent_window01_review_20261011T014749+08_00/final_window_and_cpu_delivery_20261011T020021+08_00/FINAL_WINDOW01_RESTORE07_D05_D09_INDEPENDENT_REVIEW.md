## Code Review Summary

**Files Reviewed:** 112 Window01/Restore07 evidence artifacts; D05 six canonical source blobs and CPU receipt; D09 candidate cache/test/replay source and CPU receipts.  
**Total Issues:** 1

### By Severity

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 1

### Results

- The 112-entry Window01 manifest matches exactly (`4558fa53e101e4c0d9630401891b25b0d1a1d7c4b79382332851c6ec5d250619`). η remains `failed_harness`; it has no numeric result. The prior independent raw AIPerf review supports D08 H1 under its original absolute criterion. The prior request-bound D0 addendum supports the 255-step diagnostic only.
- Restore07 matches the frozen release baseline in mode, window, chunk, running/graph values, argv, and five output/cache fields for each short and long smoke. The SDK smoke passed and live readback was healthy. Its observation remains open.
- D09 candidate `7d8d389ee5d85de7e4f8e533f35c27f4c4c02690`: receipt outputs and stderr hashes match local raw files; candidate git-blob source hashes match output pins. Enabled reaches 20282 with exact entry/snapshot and conv/recurrent/PLE cold-state equality. Default off preserves 20160 with no entry/snapshot. **Approved for CPU scope only.**
- D05 local `9d869d77fcb4da6a1c64fcbae419018a03aa36e4`: six local canonical Git blobs match the post-`git am` equivalence table; remote CPU receipt is `4a9246abfc47d9ccaf9ac483d06d2517d7b423d852f98872397f43c296b0b07c` and records 16 passing tests with the bound 13504/13554 state assertion and default-off 13376 behavior. **Approved for CPU scope only.**

### Issues

[LOW] Request-bound and generic D0 aggregates use different call counts.  
File: `evidence/window01/d0_service/d0_decode.json:1`  
The generic aggregate reports 257 calls per layer; the bound ledger reports the requested 255. The generic aggregate must not be substituted for the request-level metric until the two extra calls are documented.

### Recommendation

`APPROVE_CPU_SCOPE_FOR_D05_D09`; `SUPPORTED_PARTIAL_WINDOW_RESULTS_AND_RESTORE_READBACK`. No GPU/T16 result, eta outcome, completed observation, or production acceptance is implied.
