# E2-R040a 后补工装 CPU 证据与启动阻塞

2026-10-07 01:26：新版本采集、停车原始数据、锚点四格与后补控制器完成 Linux CPU 自检。GPU 尚未启动，本文不是启动回执或模型放行。

R040 的缺失 `capture/service_delivery.json` 使用新 `d16_native_capture_shutdown_v3.py` 与 `d16_native_process_collection_v2.py` 修复。真实子进程 SIGTERM 后封存 delivery；未产生 delivery 时仍拒绝继续。原冻结采集器和 batch71 原件保持只读。

停车采集使用新 `d16_exact_service_startup_v4.py`：索引绑定四阶段 raw、实际角色 fill_value、PID/出生、请求 UID/槽位、shape/dtype 和 SHA。独立 reader 按实际 clear_slots 语义逐位核验，不能假定所有角色清零。锚点补测保存实际请求 bytes，并在计时窗口外记录 SHA；绑定输入、独立服务 PID/出生与 OFF/ON 六臂。此前四格数量齐全但缺执行时输入 SHA，旧结果保留为部分证据。

| 证据 | 位置 / SHA256 |
| --- | --- |
| Linux 55 项 CPU 自检与实际 native Run 构造 | `/data2/FreeToken/runs/dev_D16/r040a_integrated_cpu_20261007_0108/report.json` / `48b3a34d8b7c91d8667211b799e64dd895ce1d063d04406eff7fb8bc45c02a5b` |
| 采集器要求的 canonical CPU 报告 | `/data2/FreeToken/runs/dev_D16/r040a_exact_cpu_canonical_20261007_012421/report.json` / `fb7f03b8278dd3c490e87b5c0af57a6ea83af5fe9a0f619caa8c62228bd1f8b8` |
| 复用的 55 PASS 日志 | canonical 包 `reused_pytest.log` / `115f5497b011f8dfa7ff398eddd299c063d39d50762780b5fbee2130dedb8e02` |
| 独立 R 工装修复 CPU 证据终核 | `/data2/FreeToken/runs/dev_D16/r040a_canonical_cpu_review_r_overlap/review.json` / `d71bda44d32cebfb18a3256e48c5fdf0f12ea64341144ee4c5544c7da019c473` |

canonical 包使用 `ft_d16_exact_startup_cpu/v1` schema，保留原报告和相同字节的 93 项 CPU 源码库存，没有重跑 55 项测试。用真实候选 PYTHONPATH、空 CUDA_VISIBLE_DEVICES 与 socket guard 重新验证实际 Run 构造及新 collector 导入；没有启动服务或初始化 CUDA。全包 0555/0444。严格采集器没有放宽；本包 `source_execution_ready=false`、`startup_review_pass=false`、`model_admitted=false`。独立 R 复算 93 项源码及原报告/日志 SHA，通过工装修复 CPU 证据终核。实际 strict gate 的隔离临时 fixture 绑定 17 个执行依赖后通过，随后删除；没有保留或签发真实启动许可。

启动尚缺：

1. 暂停调度路径修复方案和 R046 后补轮次的用户裁定。当前 R046 为 failed_harness，不能充当 measured 前置或 T21 画像。
2. 已批准队列位置对应的真实前置 D04 控制 pin；后补只插在当时批次结束后、T05 之前，不抢占。
3. 对实际 frozen source、候选与前置控制记录完成新的独立启动复核。CPU PASS 和测试 fixture 不能代替 `owned-gpu-test-startup-only` 回执。
4. GPU 执行后逐臂原始复算及 D04 封存；不预填 GPU 指标或放行结论。

补跑范围只包含未完成的批槽、停靠、缓存、交错和缺绑定的锚点四格。已测性能、60 题、Agent 三趟和续算四组不重复。

## 第七节裁定后的更新

用户已批准 R046a、R055 和 eff 测量树，以上第 1 条待裁定事项已解除。当前队列固定为 R048 → R040a → R045，R040a 需 R048 的 measured 控制记录。CPU 原因矩阵证明 delivery 缺失与暂停消息暂存是两个独立缺陷，见 `BATCH71_CAUSE_CPU_20261007.md`；保留 shutdown v3 与 collector v2，停靠臂使用 eff。控制器已修改到新候选与队列，旧 55 项 CPU 包只证明当时源码，不能作为修改后控制器的启动许可；到队首时核验新源码与前置清单，交独立 R 复核。

## 第十三节与 2026-10-07 13:49 新版准备

R040a移到R058之后、修复+T16之前。新入口v5/basev2/dryv4严格只接R058 measured；原v4及旧签不沿用。Linux四组件179PASS，report SHA `e412b437972438e05d3069e4c2423799f105ef5ad9a09910b7a436ac06cf6fa1`，见 `R040A_SECTION13_LINUX_CPU_20261007.json`。正式FILEDRY和独立启动签待R058封存后执行。以上旧队列、停问和候选说明为历史，最新发布树0aa23431/98304/.88与原shutdown v3/collector v4不变。
