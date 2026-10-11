# 11:45 裁定执行报告（持续更新）

真实写入时间：2026-10-10T13:25:26.872107+08:00。GPU 队列仍在执行；本页不是全部结束报告。推送未获批准，未推送。

| 项目 | 实际开始 | 实际终态 / 当前状态 | 规模与结果 | 预计结束 |
|---|---|---|---|---|
| R044b 最终工装重试 batch159 | 11:34:59 | 12:00:49 清理终结；not_met | 2 服务 / 48 调用；B1 cold/warm 第38个输出 token 180/171；后续臂停止；原始证据独审只读封存 | 已结束 |
| R067e batch160 | 12:12:30 | 12:15:57 failed_harness | 1 服务 / 0 调用；启动前就绪未完成；native 绑定修复后另开 retry1，旧判定不追溯 | 已结束 |
| R067e retry1 batch161 | 12:37:00 | 13:04:56 failed_harness | 3 服务 / 7 调用，热臂6调用有效；冷臂 donor@P 前置门抛错；精确归属清理后独审封存 | 已结束 |
| D10 干净测量 batch162 | 13:06:18 | 13:13:35 terminal 文件写入；not_met / valid_negative | 1 服务 / 2 调用，各512实际输出；预热16成对步后495共同token/路、95.706955058秒、5.172037911978515 tok/s/路；独审及原始只读封存 | 已结束 |
| D09 bd57 T16 batch163 | 13:19:26 | 在跑，尚无终判 | 计划8服务 / 100调用；默认关闭，LM与普通prefill各4臂 | 14:14–14:29（启动时预计） |
| D09 bd57 T17 | 未开始 | CPU就绪，等待本轮T16正式kept封存 | 计划6服务 / 8调用；runner provenance字面量修复曾记pre_gpu_failed 0/0，不消耗重试额度；已重新独审 | T16 kept 后约25–35分钟，实际启动时登记 |
| D05 定界诊断 | 未开始 | pre_gpu_failed，0服务 / 0调用，无额度扣减；跳过GPU | 实际bd57 CPU回放支持与D09不同源；T11历史链无法在≤2调用中重建，诊断包独审REJECT；H-bug修复方案已交付 | GPU不运行 |
| 恢复481 / SDK冒烟 | 未开始 | restore04包CPU独审与root审批已齐 | 可跑队列结束后执行；17项对照df77cb14…，失败先停481再回滚184并停止后续GPU | 暂估15:00–16:00，按实际T16/T17进度更新 |

R067e CPU 复核：历史热臂与batch161热臂的conv、recurrent、PLE conv和ngram四类状态形状、dtype、原始字节完全相同。执行包使用plain PLE名称，引擎使用`slot_states/`名称与排序，两者摘要域不同；这足以解释前置门比较摘要不一致。冷臂实际状态未留存，不能宣称冷/热已等价。本轮封存判定不变，D12冻结；未来修正包和GPU重试须另排，不插入当前已批准队列。

D10已按裁定结束原型阶段，不运行该候选T16，不进入正式开发；正式负结果写入论文§8。命中率/H2D计数已留证，但不据此归因为实现缺陷或普遍否定重叠机制。D11仍待用户批准工时，不立项、不建分支。

CPU交付：D15一页只读定位已完成；T21第8输出token的层/专家/槽号和置换事件缺少既有证据，启用路径保持停止。T14 LayeredPrefill / SLO-Weave 与D6十项差异表已完成。D06登记“已交付，由AIPerf替代；G3/G4已并入E2-R045”，代码保持默认关闭。D13继续等多卡节点。

13:00汇报已于13:02:29按真实时间提交，见`MORNING_1300_REPORT_20261010.md`；附`PUSH_APPLICATION_20261010.md`，仍未获批准。此前restore03 SDK17项比对通过；其12:24:10→12:36:32观察窗口已如实封存为TRUNCATED（13样本），不作隔夜通过。现在481停服，GPU由batch163独占。恢复后另开新观察窗口。

证据入口：`development/d10_clean_measurement_20261010/approved_measurement/actual_batch162_closure/`；`development/r067e_20261010/history/terminal_batch161_2192859_170151379/`；`development/d09_gpu_reapplication_20261010/ROOT_T16_ACTUAL_LAUNCH_CURRENT.json`；服务器append-only协调日志`/data2/FreeToken/development/night_execution_20261009/COORDINATION_LOG.jsonl`。
