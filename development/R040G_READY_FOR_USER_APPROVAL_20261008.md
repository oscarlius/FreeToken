# R040g：剩余 D16 项的一次补跑方案

2026-10-08 13:09。准备工作已完成，尚未启动 GPU。本方案申请一次 R040g 重试，并明确旧、新提交证据的汇总边界。

## 原因与执行范围

R040f/b109 已按 `failed_harness` 原地只读封存：首个 parking 服务开启开发暂停接口后，0aa 的消息接收循环延迟普通请求；14 项均未完成。现有 effb 提交已经修复此处路由，不再新增引擎补丁。

R040g 将剩余 **14 个服务、16 次生成调用**统一放在 `effb9969706922ddad9e59b96377e46469ebe97f` 的 `/data2/FreeToken/wt/e2base1-p1` 上执行：parking 4、cache 4、interleave 6。沿用 98,304 上下文预留、显存比例 0.88、原输入、逐位判据、collector、exact-ID 采集与 shutdown 路径。

已复核的历史结果保持 `0aa23431e5b800797543bdecbf35a01045131d7d` 身份：R040c 的 slots2、R040e 的 slots4、R040a 的六个锚点及此前保留结果。新旧结果分别标注来源提交；申请允许据此汇总 T20 剩余项。R055a 的六个默认关闭冷臂作为交接书 §10 既定默认路径依据；R055b 仍为失败，暂停链的实际验证仍由指定批次承担。

## 已完成的准备

- 新入口绑定的 Linux CPU 检查：6 项通过。collector、exact-ID 和 shutdown 源保持原冻结字节，沿用对应独立源码证据。
- 独立 SOURCE 复核覆盖实际 collector 消费链、18 个角色、48 个归档文件。
- 同一正式入口的真实路径空跑：14 项通过；无服务、请求、GPU 锁或正式轮次目录副作用。外部 T09 锁保持不变。
- 独立启动技术复核及 root 对实际 `require_dry_run_receipt`、`require_startup_review` 的回读均通过。技术复核保留 `model_admitted=false`、`gpu_retry_user_approved=false`。

| 证据 | 路径或 SHA-256 |
|---|---|
| 实际入口 | `/data2/FreeToken/runs/dev_D16/r040g_v1_cpu_20261008_1243/runtime/r040g_d16_remaining_prepare_v1.py` |
| 入口 SHA | `f06e1e6b09fe843a80634c93eca658466d33df9228a79898d90eafbc9fab587a` |
| SOURCE 复核 | `/data2/FreeToken/runs/dev_D16/R040g_collector_source_review_v2/review.json` |
| SOURCE SHA | `24e123f1314f8e898725f582e76a1a3ac78e0b97fd483d1e82008264843c025b` |
| FILEdry | `/data2/_shared/runs/ft_rounds/.dryrun_r040g_v1_20261008_diag/dry_run_receipt.json` |
| FILEdry SHA | `4d9291b18718fc03071de0210d67f564aba1d41dfc75589c8101caa6704b3c5f` |
| 启动复核 | `/data2/FreeToken/runs/dev_D16/R040g_startup_review_v1/review.json` |
| 启动复核 SHA | `45f855997f3a394d39af1b27d1b45d35ade96b33d96ba9ed830b508c0eb4b1a9` |
| 启动 pin SHA | `f8d961eba733c00881e552d39158c4930d7f3f71b25888d2709f1ec58554f1f3` |

## 需要裁定的边界

交接书 §8.4 规定“测量开始后（已有完成臂或已起服务）失败”需再次裁定；R040f 已启动服务。§8.6 原指定 R040a 在 0aa 上运行，本方案还涉及剩余 14 项改用 effb，并按来源提交汇总历史证据。因此需要批准这两个具体变更。

若获批准，在当前 GPU 批次结束、真实前置及锁/空闲检查通过后按现有队列启动一次。结果仍须独立逐组复算及 D04 封存；本方案不预先认定 T20 通过，也不包含发布、部署或远端推送。
