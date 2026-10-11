# E2-R048 / T09 前置门修正与业务体阻塞

2026-10-07 01:26：按交接书第六节，将 `r048_t09_prepare.py` 的 R040 前置 verdict 从 kept 改为 failed_harness。R051-gate-D08 的 kept 与 R049 的 measured 要求保持原顺序。测试同时核对完整前置表与默认拒绝执行路径。

Linux CPU 自检 18 PASS：`/data2/FreeToken/runs/dev_R048/r048_failed_t20_gate_cpu_20261007_0121/report.json`，SHA256 `1f24fab32092c407df79caefed13b081653c86303a195ea27e0c984ef52bfbeb`。空 CUDA_VISIBLE_DEVICES、socket guard；未启动服务或 GPU，未创建正式轮次。按 INTERVENTION / PLAN §8.6，不单独请求排队 CPU 包复核；临近实际 GPU 启动时由 R 复核最终冻结脚本与前置控制记录。

`BODY_READY=False` 仍然有效：D08 原候选缺少 T09 所需的 native 完成时序观测。现有 instrumentation patch 为默认关闭的开发草稿，仅通过 CPU 合约与最小语法检查，完整 native 编译及正式候选门未验证。不能把前置 verdict 修正当成 T09 完整交付，也不能激活草稿后沿用原候选 SHA。

GPU 启动仍需前置队列完成、用户对观测候选的裁定、对应门及真实业务体实现和独立启动复核。未分配新轮次、未保留 GPU 锁。

## 03:43 C1 limited CPU readiness check

Conclusion: the existing candidate `2600ada8faef6490b7a5fbdf6708e12c29d86536`
cannot supply the T09 business body within its currently emitted raw fields.
`layers/moe.py` records only host enqueue durations
(`cpu_submit_enqueue_ns`, `cpu_sync_enqueue_ns`, and
`pcie_copy_enqueue_ns`); `cpu_executor.py` exposes only cumulative worker
service counts and pin status.  The native extension has no per-task timing
accessor.  Thus neither the CPU task completion interval / aggregate barrier
wait nor a CUDA-event PCIe completion observation can be reconstructed in an
external runner, and a stream synchronize outside `_decode_hybrid` would not
pair the result with one layer's `copy_missing()`.

The minimum candidate change remains exactly the isolated draft:

1. `cpu_moe_ext.cpp`: trace-gated per-task start/end and aggregate barrier
   counters, exposed through a task-timing accessor.
2. `cpu_executor.py`: default-off propagation and retrieval of that timing for
   the pending decode task.
3. `layers/moe.py`: CUDA events immediately around hybrid `copy_missing()`,
   then trace-only stream/event completion and one per-layer record.

This changes the fixed D08 candidate.  C1's current authorization permits no
candidate/worktree edit, native rebuild, renewed T16 gate, RID, queue, or GPU
action, so this is a blocker for implementation rather than an authorized
local patch.  Root/user must approve a new reviewed candidate and its required
CPU/native validation plus `E2-R051-gate-D08` re-gate before R048 can become
body-ready.  Existing R048 admission and its default controller refusal remain
the correct fail-closed behavior.

Local evidence: draft contract tests `3 passed`; `py_compile` succeeded;
plain preparation emitted `state=queued`; `--run` raised the expected
`R048 blocked: T09 business body is not ready` before reservation, lock,
service, HTTP, or GPU activity.  Candidate worktree was clean at the recorded
commit.

## 04:57 real-path dry-run repair

The authorized D08 product candidate remains `8bf0ad3`; this repair changes
only the R048 controller's file-only branch. `start_service(..., file_dry_run=True)`
now owns service files, while `run_workloads(..., file_dry_run=True)` owns each
client JSON/ERR/LOG file. This prevents duplicate exclusive `write_new` writes
for `first_shot` and the other workload outputs. Both branches share the
service-plan writer, which creates `ENV.txt`, `SERVE_CMD.txt`, and
`serve_args.txt` before the Popen boundary. `prepare()` rejects the formal
round, every child of it, and symlinked paths before admission.

Local CPU evidence: `development/tests/test_r048_t09_prepare.py` reports
23 passed with socket and Popen guards in the complete five-arm preparation
fixture. It creates no service, lock, GPU action, HTTP request, or formal round.

## 05:02 P0 environment and parsed-arguments repair

`ENV.txt` now persists only the six explicit service fields and never inherited
environment values. `serve_args.txt` is not a pre-launch echo: formal startup
writes it only after readiness by locating `Parsed arguments` in the actual
service log; an absent marker fails closed. File-only preparation creates the
same filename solely as a CPU probe. The CPU suite includes fake SSH-password
and unrelated-secret values and confirms they are absent from persisted ENV and
command files; it also covers the missing-parser failure. Result: 25 passed.

## 07:21 current entry and freeze handoff

The authorized business entry is now `r048_t09_prepare.py` at candidate
`8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`, with parent `effb996`.  It
uses five arms in the fixed order `V0`, `A`, `B`, `C`, `S`; `S` repeats A
affinity because nativepool has no independent switch.  Each formal arm writes
the actual service plan, raw workload files (four cold cases and one two-decode
case), a D0/hybrid trace, and `round.json`.  The file-only entry is:

```bash
cd /data2/FreeToken
/data2/FreeToken/venv/bin/python runs/dev_R048/<frozen-source>/r048_t09_prepare.py \
  --prepare --dry-run-dir /data2/_shared/runs/ft_rounds/.dryrun_E2-R048
```

It must run under the same user and cwd as formal execution. It creates only
the non-RID sibling, allocates five dynamic ports, exercises every exclusive
writer, seals `dry_run_receipt.json` to 0444, and declares no service, request,
GPU lock, batch allocation, or formal RID directory. The startup review must
be a new readonly `runs/dev_R048/reviews/E2-R048_startup_review.json` bound to
that receipt SHA and the current R048/D07 source hashes.

The candidate source contract is present but remains GPU-unproven: native
`task_timing` exposes `start_ns`, `end_ns`, and `barrier_wait_ns_total`; the
trace branch records CUDA `event_elapsed_ms` and host completion observation.
Both Python gates read `FT_DEV_HYB_TRACE` with default `"0"`, and the stream
synchronize is inside the explicit trace branch. CPU tests prove only this
static/file contract. Linux freeze must run the real-path dry command above,
then R must verify the sealed receipt and startup review after R051 becomes
`kept` and R049 is `measured`; neither condition is asserted by this document.

## T09 phase and ordinary-SSE repair

`r048_t09_prepare.py` now runs the fixed five arms (`V0`, `A`, `B`, `C`, `S`) as two serial, separately recorded services using one private API/TCPStore port pair for the complete batch. The performance service clears `FT_DEV_D0`, `FT_DEV_D0_PATH`, `FT_DEV_HYB_TRACE`, and `FT_DEV_PAUSE_ENDPOINT`; it sends only ordinary SSE and records timing as network-SSE first-output-to-terminal timing. It binds actual `UserMsg` input IDs and `DetokenizeMsg` token sidecars through the copied ordinary-v3 worker wrapper and R049 ordinary client. It does not claim an `ft_dev` ACK.

The diagnostic service uses the same service arguments and ordinary payloads, then enables D0 and hybrid trace. Its figures are explicitly excluded from performance comparisons. Actual `Parsed arguments` from `serve.log` and persisted service environments are compared per phase through the frozen `d04_original/serve_args_diff.py` parser; only `_unique_suffix` may differ. The runtime closure is copied under the batch directory with Linux mode 0600, including the worker observer, ordinary client/adapter, port-pair helper, and parser. Candidate source binding includes the two actual native extensions and D08 D0/trace/argument sources.

This remains CPU readiness only: no signed startup review, GPU execution, or formal result exists. FILEDRY must prove the copied closure, pair receipt, file permissions, and dry receipt against final frozen bytes before R048 startup review.
