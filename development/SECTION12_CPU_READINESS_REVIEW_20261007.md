# §12 CPU readiness review — E2-R048 / T09

## Verdict

- **PASS (CPU preparation only).** The current R048 controller, its six bound source inputs, and the D08 candidate are consistent with the approved §12 preparation shape: five hybrid arms, 98,304-token window, memory ratio 0.88, ordinary 4,096-token prefill, and only the same-round `S` versus `V0` controlled comparison.
- **No formal file-dry, startup approval, launch, or GPU/T09 acceptance.** The reviewed Linux report explicitly records all four as false/not performed. R049=`measured` remains an enforced formal prerequisite and is not replaced by this CPU result.

## Direct evidence

| Claim | Result | Evidence |
|---|---|---|
| Linux CPU run is reproducible and bound | PASS | Remote `/data2/FreeToken/runs/dev_R048/section12_cpu_20261007_131631/report.json` SHA-256 `8f666e5706648d7492ef39a591d983d48b57a8ec4509b6755c5c83dd82dc7231` was read back and equals `R048_SECTION12_LINUX_CPU_20261007.json`. It reports 26 passed in 0.09s, `CUDA_VISIBLE_DEVICES=""`, socket guard loaded, torch not loaded, and `returncode=0`. |
| Entrypoint fixes all §12 measurement settings | PASS | `r048_t09_prepare.py:38-50` changes the inherited service command to hybrid, removes layer-major, requires ordinary 4096 prefill, and overrides both window parameters to 98,304. The inherited fixed command sets `--memory-ratio 0.88` (`d07_g3g4_prepare.py:305-316`). The measurement plan repeats `98304/.88/4096` and `comparison_scope=within_round_hybrid_S_vs_V0` (`r048_t09_prepare.py:225-244`). |
| Historical offload is not used as the controlled comparator | PASS | Both plan/result documents set `historical_offload_is_controlled_comparison=false`; the controller records the sole comparison scope as `within_round_hybrid_S_vs_V0` (`r048_t09_prepare.py:229-230`). |
| Candidate, runner, D07 helper, and tests are the tested inputs | PASS | Current local SHA-256 values equal the remote report for `r048_t09_prepare.py` (`c991329c…`), `d07_g3g4_prepare.py` (`c4a28aaa…`), and its test (`6b5ef08e…`). Candidate worktree `e2d08` is clean at `8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`. Its three source-copy hashes match the report; the server actual-byte hashes match the report's `actual_sha256`, with newline-normalized equality true. |
| Native completion-observation contract is present and disabled by default | PASS (static contract) | Candidate C++ defines default-off `trace_enabled` and exposes task start/end/barrier timing; Python enables it only under `FT_DEV_HYB_TRACE=1`. Layer code synchronizes and writes CUDA-event completion fields only in that trace branch (`e2d08/.../cpu_moe_ext.cpp:1313-1315,2067-2075`; `cpu_executor.py:60,293-294,669-673`; `layers/moe.py:423-443`). Regression checks these contracts (`tests/test_r048_t09_prepare.py:354-364`). |
| Current entry is fail-closed on formal prerequisites | PASS | `GATES` requires `E2-R040=failed_harness`, `E2-R051-gate-D08=kept`, and `E2-R049=measured`; admission checks clean exact candidate and ancestry (`r048_t09_prepare.py:23-33`). Controller then requires a sealed file-dry receipt and a bound startup review before lifecycle allocation (`:67-86,262-268`). |

## First concrete problem

None found in the CPU preparation. The candidate's source-copy versus actual-byte SHA difference is explained by line-ending normalization, and the report independently records normalized equality for all three candidate files; it is not a source drift.

## Explicit boundary and remaining proof

- **CPU support proved:** static controller/trace contract, source identity, and guarded CPU tests.
- **Formal file-dry not proved:** report fields `formal_file_dry_performed=false`, `formal_round_created=false`, and no sealed R048 dry-run receipt were reviewed here.
- **Startup not approved:** report field `gpu_launch_approved=false`; no R startup review binds a future file-dry receipt to the current source hashes.
- **GPU/T09 not proved:** `model_started=false`; no native rebuild/runtime trace, service health, workload raw file, same-round S/V0 observation, D04 closure, or T09 verdict exists. CPU compilation/static checks do not substitute for any of them.
- **Current stop condition:** R049 must be formally `measured`, then R048 must pass its same-user, same-entry formal file-dry and independent startup review before any launch decision. The queue remains stopped after R046b; this review supplies no authority to change that.

## R044/R047 queue-tail CPU repair

### Verdict

- **PASS (CPU preparation only, v2).** The repaired Linux closure bound the real E2-base.1 adapter files needed by the terminal-cap test; it passed 48 tests with an empty CUDA-visible set, socket guard active, and `cuda_initialized=false`.
- **The original CPU failure remains evidence, not a passing substitute.** v1 ran 47 PASS / 1 FAIL because `equiv_suite.service_capture` was absent from its staged base adapter. It remains sealed at its own report hash. v2 adds the exact 11 required E2-base.1 files and does not reinterpret v1 as a pass.

### Direct evidence

| Claim | Result | Evidence |
|---|---|---|
| Failed CPU attempt is retained with its actual cause | PASS | `/data2/FreeToken/runs/dev_T10/section12_tail_cpu_20261007_131754/report.json`, SHA-256 `5cf66d7d5cae6c27fea0d10e36012a4525917c5ff1ddc0c7ef82c34de695e02c`, records `passed=false`, `returncode=1`, 47 PASS / 1 FAIL, and `ModuleNotFoundError: equiv_suite`. The v2 report explicitly names it under `supersedes_failed_cpu_report`. |
| v2 result and source binding | PASS | `/data2/FreeToken/runs/dev_T10/section12_tail_cpu_v2_20261007_131927/report.json`, SHA-256 `23b9529b241ac76977b7b4bf5960c53b212f5e2901995ec02f4a3299176ad3a8`, equals local pointer `R044_R047_SECTION12_LINUX_CPU_20261007_v2.json` and reports 48 PASS / return code 0. Runner and both test hashes match current local files. |
| Real base adapter is present, not mocked away | PASS | v2 binds eleven `e2base1` Python and `scripts/equiv_suite` inputs, each with actual-byte and copy SHA plus `newline_normalized_equal=true`. Current clean local E2-base.1 is `0aa23431…`; all 11 source-copy hashes match the v2 report. The previously failing test imports the real `equiv_suite.service_capture.ServiceCaptureAdapter` and exercises its terminal-cap behavior (`tests/test_t10_e2_r044_prepare.py:41-63`). |
| CPU Torch use is bounded | PASS (CPU only) | v2 reports `torch_loaded=true` for the real small-tensor adapter test, while `CUDA_VISIBLE_DEVICES=""` and `cuda_initialized=false`; socket guard is loaded. This proves neither CUDA execution nor model startup. |
| 98,304 window and 0.88 ratio are fixed in both tail entries | PASS | R044 rewrites both window arguments to 98,304 while inheriting the D07 fixed 0.88 ratio (`t10_e2_r044_prepare.py:185-198`; `d07_g3g4_prepare.py:305-316`). R047 directly specifies `--memory-ratio 0.88`, both 98,304 arguments, and ordinary 4,096 prefill (`t03b_e2_r047_prepare.py:157-175`). |
| R047 cannot treat the R046b failed_harness as measured | PASS | R047 requires `E2-R046b=measured` among formal predecessors (`t03b_e2_r047_prepare.py:46-47`); regression rejects `E2-R046b=failed_harness` (`tests/test_t03b_e2_r047_prepare.py:86-105`). R044 separately remains gated on `E2-R052=measured` (`t10_e2_r044_prepare.py:43-47`). |

### Boundary and stop condition

- Both reports mark `formal_file_dry_performed=false`, `formal_round_created=false`, `gpu_launch_approved=false`, and `model_started=false`. No formal file-dry receipt, R startup review, GPU service, HTTP workload, raw measurement, or D04 closure was performed.
- R047 remains blocked until a real E2-R046b `measured` closure exists; its current failed-harness closure cannot satisfy that exact gate. R044 likewise needs E2-R052 `measured` before execution.
- This CPU repair ends at source/adapter and controller proof. It does not authorize a queue change, launch, or acceptance verdict.
