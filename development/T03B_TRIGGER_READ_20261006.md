# T03b / E2-R047 trigger probe readme

`t03b_e2_r047_prepare.py --emit <new-path>` creates a review-bound six-arm executor from the verified batch29 template. It preserves A/B ABABAB ordering and makes `--no-prefill-anchor-cut` the only A/B launch difference. The generated executor requires an explicit `--run` and a candidate-bound approval receipt; it cannot allocate a batch number.

Each arm enables business D0, runs the same multi-round thinking load, and binds each later turn to the actual prior reasoning/content. It stores raw SSE events, records `first_token_s` only at the first nonempty reasoning/content delta, and takes `cached_tokens` from the final usage packet. Each arm retains its own final `serve.log` and writes `snapshot_count.json` from exactly one final `D0 anchor_snapshots_taken=N` line. Cache donations are never substituted.

The local and remote `batch29_E2-R008_python.sh` SHA256 is `19ad60685d8fcb9942535dc3268e72ea205ceed4e2152ba8a569328faf2daad0`. The preparation script performs no service, CUDA, or model-port action unless the later reviewed executor is approved and launched.

## Linux CPU stage (2026-10-06)

Stage: `/data2/FreeToken/runs/dev_T03b/cpu_stage_20261006`. With `CUDA_VISIBLE_DEVICES=''` and `T03B_TEMPLATE_PATH=/data2/FreeToken/runs/plan_batches/batch29_E2-R008_python.sh`, the FT venv self-test and all eight pytest cases passed; `--emit emitted_r047.py` and `py_compile` passed. No server, 8095 connection, batch allocation, or GPU task was started. Stage SHA256: prepare `5496c4a015281a4af9440f040d9816d8b261118434c7c7afdf4894983682c478`; tests `6bf738d72175e8029fc50d3c26675ae239f41acb5257249d43d8059be906fdc3`; emitted executor `fb1a3ea262462ad05f08e4598d3efcea2ce22c819cb86c40aeacfdac2c887e36`.

## R047 launch repair (2026-10-06, local CPU only)

development/t03b_e2_r047_prepare.py now emits a controller/child executor. The controller checks the clean candidate, formal closed-round gates at their actual verdicts, and the actual E2-R043/E2-R042 development result plus matching cleanup receipts before a single atomic batch reservation. It publishes the exact child PID/start-ticks binding; the child verifies that receipt before any GPU lock or idle check, then repeats admission.

The review receipt must bind the emitted executor, prepare source, batch29 template, and immutable load/input SHA. The emitted six arms remain ABABAB, use one serially reused dynamic port, preserve the 49,152 window and host-slots 0, and differ only by --no-prefill-anchor-cut. The pinned sibling d04_original/serve_args_diff.py parser (SHA-256 61ef1c553ef383cfa59c2cec609528ed9cde8998061c354224a17b497948bd21) requires model path, server port, special-token checkpoint, PID suffix, and cut fields. It stops on any difference outside _unique_suffix and the A/B cut field.

Result output remains pending_review with proposed_verdict=measured; it records six real arm snapshot counts, cached-token readings, and TTFT values. All-zero D0 counts produce coverage_not_achieved, not a completion claim. Cleanup uses the shared owned lifecycle and keeps the GPU lock when an owned process group survives.

Local validation: Python 3.14 py_compile, pytest development/tests/test_t03b_e2_r047_prepare.py -q = 18 passed, and --self-test passed. This did not run --run, start a service, use CUDA, contact 8095, allocate a batch, or acquire a GPU lock. Source SHA-256: bac6c8e738568414a010210c6f39a8dc7e91b1a18993bdb1aad2d1491889ebfb; test SHA-256: a71413a250c5f3e7ec624dfbeddbb00e12a29fba8e34625bd815196880f3a8c6.

R047 still requires its real formal closures, one complete matching R043/R042 development receipt pair, a current review receipt for the emitted bytes, and queue/idle approval before any GPU action. No D04 formal closure or measurement verdict is created here.

## Fresh Linux CPU evidence (2026-10-06)

Current source was staged as /data2/FreeToken/runs/dev_T03b/cpu_stage_20261006_2105, separately from earlier CPU packages. Under /data2/FreeToken/venv with CUDA_VISIBLE_DEVICES empty and the existing dynamic socket guard first on PYTHONPATH, py_compile, the complete T03b test file, and --self-test passed: 20 passed, CPU_GUARD PASS. No --run, service, endpoint connection, GPU lock, or batch allocation occurred.

The staged source, test, and parser SHA256SUMS are respectively 60eab6d733ef5d2e8d1ed06a38f629a8c54fee6e4909ccff9622b0f8ce1042ac, 5c0a4b90c07c64276367c7d60deb0e801a1d5c0feba0cc8b8811bcc73f26675b, and 61ef1c553ef383cfa59c2cec609528ed9cde8998061c354224a17b497948bd21. The stage is sealed read-only: directory mode 555, source and test modes 444.

This CPU evidence proves only launch-control and parser behavior. R047 remains blocked from a GPU launch until queue formal closures, complete R043/R042 receipts, current byte-bound R review, and live idle/queue admission are all present.

2026-10-06 21:02:33 CST：根复核以只读方式复用cpu_stage_20261006_2105，外部报告 /data2/FreeToken/runs/dev_T03b/cpu_verification_20261006_210200/report.json，SHA 0e94fd79da19b74fe5ea74d1695c8ddeb0e56eb7274b274384bdf0cb3268941d。FT Linux venv真实OS exit0，20 PASS、self-test exit0；CUDA隐藏、动态guard、全部endpoint connect拒绝、live GPU lock未变。原source/test SHA与本地交付一致，原包未修改。目录名2105是标识，不作为执行时间；协调日志先前21:10条为错误时间，正式复核时间见本报告executed_at_cst。
