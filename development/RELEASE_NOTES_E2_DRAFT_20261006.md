> 10-09晚间更新：D09/D10及X-STRATA-R002-mini已批准，GPU按[新队列](../plan/EVENING_DIRECTIVE_20261009.md)；mini在v0.1.39的无MTP HTTP服务被源码门阻塞，未测。推送仍待10-10 09:00观察报告后的申请与批准。下文“Strata未批”仅是旧状态。

# E2 发布说明（481d3a7已部署，限定冒烟通过）

**最终状态（2026-10-09晚间）：481已恢复serving，最终恢复冒烟1 passed/0 skipped、独审PASS，首次冷基准行结构/SHA/usage一致。** R045已完成4请求，decode22.42/22.53/22.03/22.21 tok/s，not_met。R067c原轮与两次工装重试均failed_harness，实际分别1/1、0/0、1/3，0可比较格，完整原始/D04封存；重试额度耗尽，不再自动GPU重试，≤64与论文C3仍待证。最终恢复审批RESTORE481-E2-R067c-20261009-03。只读观察已启动至2026-10-10 09:00，推送待观察后用户批准；Strata未批。详见[R045结果](R045_RESULT_20261009.md)、[R067c结果](R067C_RESULT_20261009.md)。

候选从0aa23431经4c878f6、d577e32到481d3a7，首段含9个提交，不能写成单一补丁。新候选包含OOM worker恢复和公开API恢复期间准入协议；完整父链、默认门/恢复门与路由范围见[候选链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)。发布配置98304/.88、running/graph2、层优先4096、pinned PLE、NVFP4 Triton、GPU0；回滚保留184c965普通8192、49152。

| 已有证据 | 限定结论 |
| --- | --- |
| T17 | 逐位等价覆盖已测尾段≥65；≤64含1走不同分支，GPU正确性待证。 |
| D16/R066系列 | 单请求冷可复现、同结构热/冷与指定并发分别记录；不能宣称temperature0任意并发全文不变。R066c五条字面文法异常按用户口径分类c，不证明普遍任务合规。 |
| R056 | 98304配置完整87100提示已测，32K解码中位34.33tok/s，对旧73728的38.30约下降10.4%；跨窗口代价，非同配置回归结论。87K请求后约0.357GiB为采样。 |
| R058 | 双会话已测最低采样377.7MiB，约378MiB；依赖OOM恢复兜底，不保证所有业务余量。 |
| R061f | chat路由一次故障注入；已验受影响请求错误、排队恢复与新worker冷参照一致。其它路由没有分别故障注入。队列默认128、ready等待900秒与481一致；只实际观测1个排队请求。 |
| R067 / D20 | b132/b133保留历史failed_harness；b134实际1 service/0 generation/0 cell，controller 名称被 artifact loop 覆盖后由根代理按 PID birth TERM，终态 failed_harness。累计3 service/1 request attempt/0 valid；cleanup_errors[]、GPU4MiB/compute空、锁释放。修复仅新CPU v2，local/Linux各5项及独审PASS；完整重跑需10 additional，超原后缀cap；新R067c/b135已运行1服务/1调用后failed_harness，0可比较格；生产已恢复并通过首次冷基准冒烟，retry1尚CPU准备。≤64仍待证。 |
| R045 | 旧v18在reserve前阻断并保持停止；替代481 AIPerf已按16:30指令不停服完成4请求，decode22.03–22.53，not_met，独审确认。 |

FTD-20261009-1已只读发布，论文v5/v5.1已完成各自审查；旧FTD、failed/not_met、v5原件不变。R063a仅E3 D12默认关闭证据，E3优化和D20不随本次发布激活。Strata22服务/345调用仍未批准；E3禁用8095/8096。

停服/恢复/冒烟必须有本次审批号并占用同一共享锁；生产常驻，已批准测试按16:30授权自行停服并记录，结束后恢复481及首次冷基准冒烟，无需逐次申请。本次生产PID与冷SHA/usage已经生成；监控继续运行，未宣称长期观察或业务验收完成。本说明不把分支、CPU通过或健康HTTP当成业务验收。

## OPSv2 发布前状态

OPSv8服务器包CPU65 passed/0 skipped；H2 对 release/rollback 在相同 allowlist 下通过。当前 pinned 发布配方仅绑定 gate 精确匹配的 `_cpu_moe` 和 `_pinned_tensor` 实体，row_store 只在 generic disk 默认路径所需而不在本配方；详情见 `ROW_STORE_FROZEN_CPU_PROOF.json`。原候选首次部署失败并回滚的原件保留；本次OPSv8重新部署481已通过独占冒烟并登记内网放量。R067c及已批准测试停服由16:30授权覆盖；推送须观察至明早后另批，Strata未批准。

本次重新部署冻结源码及当时手册快照保留在OPSv8/source；当前文档的现场状态更新不覆盖冻结源码。生产使用source_manifest SHA029add4d8ca253ae64a8a34350f2287ab9e72acd631f049cc362d7e4921d5429。
