# E2 发布说明（候选冒烟失败，已恢复184c965）

本次条件发布 `DEPLOY-E2-20261009-COND-01` 达到 serving 后，独占SDK/pytest冒烟 **1 failed、0 skipped（exit1）**：8257提示的Prefill日志为512+7745两行，固定4096断言要求3行。候选未放量、无已签冷基准，已完整停止；按已有授权 `ROLLBACK-E2-20261009-COND-01` **恢复184c965，health=serving、回滚冒烟1 passed/0 skipped（exit0）**。当前49152窗口/普通8192、running/graph2，supervisor2887078/service2887095与GPU锁身份已核实；回滚自己的SHA/usage基准已保存。推送、R067c、R045和Strata均未执行。完整结果见[部署结果](DEPLOY_RESULT_20261009.md)。

候选从0aa23431经4c878f6、d577e32到481d3a7，首段含9个提交，不能写成单一补丁。新候选包含OOM worker恢复和公开API恢复期间准入协议；完整父链、默认门/恢复门与路由范围见[候选链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)。发布配置98304/.88、running/graph2、层优先4096、pinned PLE、NVFP4 Triton、GPU0；回滚保留184c965普通8192、49152。

| 已有证据 | 限定结论 |
| --- | --- |
| T17 | 逐位等价覆盖已测尾段≥65；≤64含1走不同分支，GPU正确性待证。 |
| D16/R066系列 | 单请求冷可复现、同结构热/冷与指定并发分别记录；不能宣称temperature0任意并发全文不变。R066c五条字面文法异常按用户口径分类c，不证明普遍任务合规。 |
| R056 | 98304配置完整87100提示已测，32K解码中位34.33tok/s，对旧73728的38.30约下降10.4%；跨窗口代价，非同配置回归结论。87K请求后约0.357GiB为采样。 |
| R058 | 双会话已测最低采样377.7MiB，约378MiB；依赖OOM恢复兜底，不保证所有业务余量。 |
| R061f | chat路由一次故障注入；已验受影响请求错误、排队恢复与新worker冷参照一致。其它路由没有分别故障注入。队列默认128、ready等待900秒与481一致；只实际观测1个排队请求。 |
| R067 / D20 | b132/b133保留历史failed_harness；b134实际1 service/0 generation/0 cell，controller 名称被 artifact loop 覆盖后由根代理按 PID birth TERM，终态 failed_harness。累计3 service/1 request attempt/0 valid；cleanup_errors[]、GPU4MiB/compute空、锁释放。修复仅新CPU v2，local/Linux各5项及独审PASS；完整重跑需10 additional，超原后缀cap；新R067c独立10/14范围已获批，但本次部署失败，且停服窗口未批，不执行。≤64仍待证。 |
| R045 | 旧v18在reserve前阻断并保持停止；替代481 AIPerf CPU计划为2服务/4 generation calls，部署后需新admission。 |

FTD-20261009-1已只读发布，论文v5/v5.1已完成各自审查；旧FTD、failed/not_met、v5原件不变。R063a仅E3 D12默认关闭证据，E3优化和D20不随本次发布激活。Strata22服务/345调用仍未批准；E3禁用8095/8096。

停服/恢复/冒烟必须有本次审批号并占用同一共享锁；生产常驻，测试按需申请停服。正式激活后才会生成生产PID、冷SHA/usage及观察记录。本说明不把分支、CPU通过或健康HTTP当成业务验收。

## OPSv2 发布前状态

OPSv6.1服务器包CPU48 passed/0 skipped；H2 对 release/rollback 在相同 allowlist 下通过。当前 pinned 发布配方仅绑定 gate 精确匹配的 `_cpu_moe` 和 `_pinned_tensor` 实体，row_store 只在 generic disk 默认路径所需而不在本配方；详情见 `ROW_STORE_FROZEN_CPU_PROOF.json`。本次候选冒烟失败并已停止，184c965已恢复并通过自身冒烟（1 passed/0 skipped）。推送、R067c/R045每次停服和Strata仍未批准。
