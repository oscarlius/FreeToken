# D08 与 T11 新 GPU 验证提案

状态：尚未获得本提案的 GPU 执行批准。两次已测量失败均已原地只读封存，下面只申请新轮次，不改旧判词。

## 可分别批准的两个范围

| 范围 | 新轮次与实际计划 | 启动条件 |
|---|---|---|
| A：D08 修复后的验证 | 先 `E2-R051a-gate-D08`：4 个服务、48 次生成调用；实际 kept 后，完整 `E2-R048b` T09：最多 10 个服务、60 次生成调用 | R051a 的 CPU/默认 FILEdry/独立 R 技术启动签已齐；R048b 必须在 R051a kept 后再做默认 FILEdry 和新启动签 |
| B：T11 收尾修复后的重跑 | `E2-R052a`：1 个服务，8 次轨迹重放 + 1 次续问，共 9 次生成调用 | CPU/默认 FILEdry/独立 R 技术启动签已齐 |

两个范围均批准时，最多 15 个服务、117 次生成调用，严格串行。T09 的 C 臂只沿用已定义的 NUMA node1 可用内存 115 GiB 条件；若该条件导致 C 的两个阶段跳过，合计为 13 个服务、105 次调用。这是既有条件，不是新降级方案。HTTP health GET 不计作生成调用。

## A：D08 根因与修复

R048a/b106 的 V0 性能 6 请求已留下局部证据；诊断在 CUDA Graph capture 内执行 `stream.synchronize()` 而失败。graph replay 不再执行 Python forward，因此仅跳过 capture 时的同步无法产生后续每步诊断数据。

新提交 `76af7584d7595d9cc52dcd60deff3aacdae1d9d6` 在独立本地工作树完成后，以 Git bundle 同步到 `/data2/FreeToken/wt/e2d08-capture-trace`。修复在 capture 时保留可重放的 CUDA events，在实际 batch 完成之后观察逐层 PCIe event 与 native CPU 计时。观察器拒绝缺层、重复层、无效/零计时及不推进的旧记录；图重建与关闭先销毁图再释放事件。诊断默认关闭，保留 graph 执行与既定测试配置。

CPU 与来源证据：

- 新候选本地及 Linux 各 17 项针对性测试通过；Linux 实际导入 6 个模块均来自新工作树，CUDA 未初始化。
- C++ 源对 `8bf0ad3` 无差异，两个 native `.so` 为逐字节校验后的普通文件副本；旧 native 证明与当前 Python 证明分列记录。新 provenance：`/data2/FreeToken/runs/dev_T16/r051a_capture_trace_native_provenance_v1.json`，SHA `a27531136810e6dd84bb896fef688644b01eb0ca7f3acb68fbbe163c9a26cadf`。
- T16 运行源：`/data2/FreeToken/runs/dev_T16/r051a_v1_cpu_20261008T022956Z/source`，Linux 29 PASS，source manifest SHA `5bd29b01b903db1630693d68c6b199e08379b8b2c60468496e58e5943ad417b7`。新 pinned protocol 与旧版仅两个窗口值 `49152 → 98304` 不同；旧源保留。
- T16 默认 FILEdry：`/data2/FreeToken/runs/dev_T16/reviews/E2-R051a-gate-D08_file_dry_run_v1.json`，SHA `62d13d8f7a708875d2af22a00975113b79e2c4b43f043975021a1bfb1e8ade3d`；真实四臂文件写入、实际默认消费者通过。
- T16 独立 R 启动签：`/data2/FreeToken/runs/dev_T16/reviews/E2-R051a-gate-D08_startup_review_v1.json`，SHA `1b44c2dc92128bc95cf7fa0f40b893e7d0e0cb4d0a42f050d5d850a6e3d4ab16`。这是技术就绪签，明确不授予用户 GPU 权限。
- T09 v11：`/data2/FreeToken/runs/dev_R048/r048b_v11_cpu_20261008_1033/source`，Linux 64 PASS，source manifest SHA `3cfb53e37eba4ce18322004e508c2999316917905293f6edd7446d40ff6d107b`。独立 R CPU_SOURCE 条件 PASS：`/data2/FreeToken/runs/dev_R048/reviews/E2-R048b_cpu_source_review_v11.json`，SHA `c1fd360957e5efadcf5614320b2fb7486396070e880c450a03f4665702099fd4`；默认 FILEdry 和正式启动签等待新 T16 实际 kept。

R051a 父树为 `effb9969706922ddad9e59b96377e46469ebe97f`，四臂为父/新候选 × D0 on/off，offload、layer-major、98,304/.88，trace/fault/pause 关闭。每臂 1 次 say-ok readiness + 1 次冷等价 + 5 single + 5 multi，共 12 次；完整输出、token、prefill tail 与 D0 判据保留。

R048b 仍为 V0/A/B/C/S 各性能与诊断两阶段，98,304/.88、hybrid、ordinary prefill、max-prefill 4096。新 trace 消费端要求每个序号完整 48 层、连续步序号、native 计时推进、真实 post-replay 标志及至少两步实际 replay。旧 b106 V0 观测不与新 S/A/B/C 拼接，不用全零替代诊断数据。

## B：T11 根因与修复

R052/b107 在 8 次重放和续问后，第二次 SIGTERM 打断 scheduler 关闭，worker 回执为 failed，故 T11 未接受。27 个原始文件已 D04 封存并经 R 复核。

v7a 的 shutdown bridge 首次 SIGTERM 触发原 scheduler 关闭，后续同类信号在关闭回执 fsync 完成前被吸收；完成之后才恢复旧 handler。真实异常仍记录 failed，外部超时后的 owned-process SIGKILL 保留。Linux spawn 回归经过实际 `_run_scheduler` 函数与两次真实 SIGTERM：旧 v1 对照失败，新 v2 完成且只执行一次 scheduler shutdown。

- 源：`/data2/FreeToken/runs/dev_R052/r052a_v7_cpu_20261008T022943Z/source`；entry SHA `695d9816694aa2d461e7723155ecce8a4ca3cf43f856925a1c72b88548ed01a4`。
- 本地 68 PASS / 6 Linux-only skip；Linux 74 PASS。source manifest SHA `fb4c75daae2359516d9daf9669fef895b49c82e67ab08e3921a140001b1ad9af`。
- 默认 FILEdry：`/data2/_shared/runs/ft_rounds/.dryrun_R052_v7a_E2-R052a/dry_run_receipt.json`，SHA `5edc20193ade2a89818f2b0f46f5fbd9f28f7eaba733c135d7fa875699ea5a02`。
- 独立 R 签：`/data2/FreeToken/runs/dev_R052/reviews/E2-R052a_startup_review_v7a.json`，SHA `3e5307352ead82bededc9b958f495b77ea71f5098edb657e11a6457781b5bcc6`。root 实际无参 FILEdry/签字消费者及 admission 均通过。

候选仍为 `0aa23431`，98,304/.88，冻结反向轨迹与目标 index7 不变，保留 R041/T20 失败元数据和 §8.7 固定 R045 顺序例外。旧失败轮保留；本次需要完整新 9 请求，不复用旧局部结果作为正式结论。

## 批准边界与工期

[交接书第八节第4条](../plan/CODEX_HANDOFF_20261006.md) 要求“测量开始后（已有完成臂或已起服务）失败”停下询问用户。R048a 和 R052 均已启动真实服务并完成请求，所以这两个修复后的 GPU 重跑需要新批准。CPU、文件空跑和 R 技术签字不代替该批准。

两个范围可分别批准；本提案不代替此前仍待回复的 R049b、R040f、R060c/R061b 请求。release/e2、部署与推送依原边界另行裁定。

当前剩余计划为 10 批、最多 59 次服务生命周期、642 次生成调用，另有 OOM worker 重启。同类 T16 既有启动到封存样本约 27–46 分钟，可作新 R051a 的条件参考；T09/T11 等缺少完整同类样本，不能给出可信总完工小时数。详见 `SECTION14_REMAINING_ETA_V2_20261008.md`。
