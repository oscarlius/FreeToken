# 2026-10-09 条件部署结果

状态：**候选481冒烟失败、未放量；按用户已有授权恢复184c965，serving及独占冒烟通过（1 passed、0 skipped、exit0）。** 本次部署失败分支已执行完毕；没有重试候选或启动后续GPU轮。

## 部署前置

release-e2 与冷 D20 的 `_cpu_moe`、`_pinned_tensor` 已逐字节复制 gate 实体，两个 SHA 完全相同；重编译资产已归档，不用于发布。row_store 已移除。它仅对本次**显式 pinned 配方**可选；通用默认 disk 仍依赖 `_row_store`。源码文件和行号见 [前置核验](deploy_conditional_20261009/BINARY_PRECONDITIONS.md)。common manifest SHA `a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18`。local/Linux CPU各48 passed、0 skipped，H2及独立前置审查PASS。

## 候选发布失败

审批 `DEPLOY-E2-20261009-COND-01`，源码481d3a7，98304窗口、running/graph2、层优先4096。服务实际达到 serving；官方SDK+pytest执行512/8257提示、各128输出，最终 **1 failed、0 skipped，exit1**。没有外来prefill的exit75/invalid记录，因此按用户指令进入回滚。

首个失败位于 `development/release_e2_ops_v2/test_smoke_live.py:42`：长请求的后端记录为两行 `512 + 7745 = 8257`，两行cached均0；工装按4096要求3行。两条API原始usage分别512/128/640和8257/128/8385，finish均length；API cached字段缺失保留为missing，未补0。长请求在日志断言处中止后续校验，不能宣称它已通过全部正文/接口检查。未生成候选的 `cold_baseline.json`，没有可签字的发布首次冷SHA基准。

只读源码定位：候选 `scheduler/status.py:78`、`:87`记录调度batch的token快照；`scheduler/prefill.py:170`—`:178`允许层优先将整个remaining prompt作为一个batch，模型内部再切块；`:400`绑定单pending请求。该证据支持冒烟固定行数假设与层优先日志语义不一致，不证明模型所有检查通过。本次未修改冻结冒烟判据或产品源码，也未重试481。

## 停止与回滚

`STOP-E2-20261009-COND-01` 停止命令exit0；stopped回执resources_released=true、errors=[]。再次核验compute为空、8095/8096无监听、GPU4MiB、lock/active/quarantine均不存在后，才启动回滚。

回滚审批 `ROLLBACK-E2-20261009-COND-01`，原树184c965，49152窗口、普通8192、running/graph2；不切换或覆盖候选树。supervisor2887078/service2887095，出生身份和GPU owner保存在回执中。回滚独占冒烟使用同一冻结SDK/pytest工装，**1 passed、0 skipped，28.58秒，exit0**。复核health=ok/serving、active/owner完全一致、supervisor/service出生、共享锁inode/device/token、生产监听与GPU worker，全部通过。没有新增OOM注入或长期业务验收。

回滚自己首次冷基准文件SHA256：`4cf527c0445c5540b2259904864250f50ec1ba1c25ed8567bbbfd6ac6934d3de`；不与481或历史graph4跨版本比较。

| 请求 | 正文SHA256 | usage（prompt/completion/total） |
| --- | --- | --- |
| 512 | `fd11a31559daaafb889b8a80f29a412470e0635caae631971a0a31e948a9dfdd` | 512/128/640 |
| 8257 | `353a97499e5df4f9689b6012f0379a322e56cddbf32fe6d36234fcf62ac4b510` | 8257/128/8385 |

finish均length，后端cached均0；API cached缺失保留null。运行回执见[回滚恢复证明](deploy_conditional_20261009/ROLLBACK_RESTORED_RECEIPT.json)。

## 证据与后续边界

失败发布27个原始文件416585字节已逐文件SHA回收，manifest SHA `b3dbd266b4ae87d57a9f8713cd0c5a9d19e9f3199d48e87209e39f779ae3655c`。服务器原件保留在 `/data2/FreeToken/runs/production/DEPLOY-E2-20261009-COND-01`；本地见 [证据清单](deploy_conditional_20261009/FAILED_RELEASE_EVIDENCE_MANIFEST.json)与[失败回执](deploy_conditional_20261009/DEPLOYMENT_FAILURE_RECEIPT.json)。

R067c10服务/14调用和R0452服务/4请求均未启动：部署成功的前提尚未满足；后续每次停服仍须单独用户审批。Strata22/345和push未批准且未执行。既有R067b、FTD、论文及原始失败轮次未改。

回滚28个文件快照451914字节已回收，运行中日志仅标为捕获时点快照；[回滚证据清单](deploy_conditional_20261009/ROLLBACK_EVIDENCE_MANIFEST.json) SHA `9bed9c7c5009a2fb95233f202492be093c416eba8bdcdd227ec795f27ffdf7c0`。当前文档修订前的五份原件保留于 `release_history/pre_smoke_failure_20261009/`，既有条件部署前归档也保留。
