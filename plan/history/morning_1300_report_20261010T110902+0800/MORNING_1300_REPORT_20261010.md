# 2026-10-10 13:00 汇报草稿（13:00 前）

**实际写入时间：** 2026-10-10T11:04:32.729808+08:00  
**状态：** `DRAFT_PRE_1300_NOT_FINAL`。13:00 是汇报检查点，不是截止或既成终态；由 root 在实际 13:00 观测后决定最终定稿。本文件不预写未来测量、生产、观察或推送结果。

## 证据边界

代码/CPU 验证、GPU 实测、生产观察和推送是相互独立的证据。CPU 通过不等于 GPU 准入或产品验收；历史终态不因后续准备而改变。

## 已封存批次

| 批次 | 轮次 | 当前事实 | 边界 |
|---:|---|---|---|
| 153 | D09-T17 retry1 | `failed_harness`；3 服务、4 调用，P 点冷/热状态哈希不同，输出比较作废。 | 历史失败保持；bd57 新协议准备不改写它。 |
| 154 | R067d-retry2 | `failed_harness`；1 服务、1 私有调用，`/internal/t17/exact-ids` 返回 404，0 次有效生成。 | C3/产品结论未建立。 |
| 155 | D10 prototype | `not_met`；1 服务、2 请求，逐请求 decode TPS 为 0.872512 和 6.967070。 | 两版原型均未达门；不能区分机制与冷启动。 |
| 156 | T03b | `kept`；6 服务、24 调用。 | 原始封存记录不能判定 UID2 的 192 token 命中来自哪一个快照来源。 |
| 157 | R044b | `failed_harness`；B1 有 24 调用，B2 未启动。 | 产品比较未发生；retry1 是新的独立轮次。 |

## 当前执行状态

- **R044b retry1 / batch158：** 已于 11:00:16 启动，状态为 active；上限为 6 服务、144 调用、并发 1、5400 秒绝对上限，早停或最迟 12:30。独立 CPU 14 项、canonical `631465…` 和 root admission `990b88…` 已由当前执行记录绑定；该状态不是终态或产品结论。
- **481 生产恢复：** restore01 的官方 SDK 17 字段对 df77cb 基线已通过；观察器收集 10 个样本后于 10:59 截断，因为 batch158 已独立准入。future queue-empty 时才可使用 restore02；其 root-ready review 为 `7113a49…`。本草稿不把恢复或观察写为后续通过。
- **D09：** 新 bd57 协议独审为 `8d41b826…`，当前 manifest 为 `80e576…`、CPU receipt 为 `a85410…`；正式 T16 仍要求新的 8 服务/100 调用闭环后才可进入 T17 的 6 服务/8 调用门。新的 GPU 申请已发出，仍待批准；本草稿不授予 GPU 准入。
- **D10：** batch155 的 `not_met` 保留。新 CPU 计量/预注册准备不改变终态；最新用户裁定下 D10 禁止 GPU。
- **T03b：** 独立 CPU 来源验证以 `a991…` 为当前证据，证明 192 与 256 状态不同；它不反向确定 batch156 中 UID2 的 192 token 命中来自哪个快照。
- **R067e：** CPU 独审 `abeb494…` 已通过，但 55–70 分钟压力知悉仍待用户回复，未启动 GPU。
- **S4：** 原生指标独审 `25982bc…` 与 paper current `64a0f6…` 已记录。原 128 输出为 45/60、每请求 TPS 为 21.978/48.034；fixed-256 实际输出 105/512，仍无效，不能称两路均超过 30，也不能作 pure-MTP 因果结论。

## §11 共享 CPU 回放

共享回放不是“5 个协调事项耗时 14.86 秒”。其真实含义是：真实 Effects 构造、spawn 服务工厂/路由以及有界 driver-idle 清理路径的 **5 个 CPU 测试在 14.86 秒通过**。该回放未启动 GPU、HTTP 或服务。记录文件为 `D:/00.开发/2026/03-模型实验/freetoken/freetoken/development/shared_harness_replay_20261010/ROOT_ACTUAL_REPLAY_1048.json`，JSON SHA `4492420c…`，日志 SHA `6d694a7d…`。

## 下午队列

1. batch158 是当前唯一已启动 GPU 工作；按其早停规则或绝对上限自然结束。
2. R067e 仅在压力知悉和独立 CPU 准备都满足后才可再评估。
3. D09 GPU 申请仍待批准；D10 未获授权，不能入队。
4. 队列为空时，才由 root 按 restore02 的既定条件决定 481 恢复；本草稿不执行该动作。

## 推送

推送仍未获批准。申请范围保持 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`、40 commits、91 files；本草稿不推送。

## 当前来源

- 当前执行记录：[MORNING_EXECUTION_CURRENT.json](../development/night_execution_20261009/MORNING_EXECUTION_CURRENT.json)，SHA `43726555…`。
- D09 独审：[INDEPENDENT_CPU_PROTOCOL_REVIEW_CURRENT.json](../development/d09_gpu_reapplication_20261010/INDEPENDENT_CPU_PROTOCOL_REVIEW_CURRENT.json)，SHA `8d41b826…`。
- restore02 root review：[ROOT_FINAL_REVIEW.json](../development/morning_restore02_20261010/ROOT_FINAL_REVIEW.json)，SHA `7113a49…`。
- 共享回放：[ROOT_ACTUAL_REPLAY_1048.json](../development/shared_harness_replay_20261010/ROOT_ACTUAL_REPLAY_1048.json)，SHA `4492420c…`。

旧草稿原字节已归档于 `D:/00.开发/2026/03-模型实验/freetoken/freetoken/plan/history/morning_1300_report_20261010T110432+0800/`。机器可读附录见 [MORNING_1300_REPORT_20261010.json](MORNING_1300_REPORT_20261010.json)。
