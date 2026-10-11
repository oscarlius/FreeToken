# 2026-10-09 冒烟修复后重新部署

状态：**重新部署481d3a7成功，serving、独占SDK+pytest及预期参考比较全部通过，已按预批登记内网放量。** 这是部署冒烟接受，不代表长期观察或真实业务任务验收。

OPSv7原包和BLOCK审查保留。最终OPSv8在 `/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded` 冻结27源码，source_manifest SHA `029add4d8ca253ae64a8a34350f2287ab9e72acd631f049cc362d7e4921d5429`。本地/Linux FT venv CPU全套各65 passed、0 skipped；独立源码、服务器hash、JUnit审查PASS。

Claude提供的58项CPU修复保留；补7项执行入口回归：首次预期参考无条件生效，结构/SHA/usage/window四种改变会失败；campaign持久化两代身份、崩溃/普通失败/并发/参考改变拒绝；实际run_smoke入口首次invalid75、第二次invalid1、第三次SDK前拒绝。未修改481产品源码或gate原生二进制。

本次预期参考来自原失败部署原始SDK响应离线重验，不是旧冒烟通过签字，也不替代本次现场冷基准。long[512,7745]，正文SHA `9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c`，usage8257/128/8385；short SHA `fd11a31559daaafb889b8a80f29a412470e0635caae631971a0a31e948a9dfdd`，usage512/128/640。初次release始终比较该冻结参考，optional BASELINE不能关闭它。

用户已有条件预批，审批 `DEPLOY-E2-20261009-REDEPLOY-01` 已写入新run与服务器/本地协调记录。停止旧184审批 `STOP184-E2-20261009-REDEPLOY-01` exit0；核验GPU计算进程/8095/8096/active/lock/quarantine均释放、显存4MiB后，启动新release supervisor3015442/service3015453。沿用98304/.88、running/graph2、层优先4096、mamba host0、显式pinned和相同两个gate实体。

等待阶段只调用health；正式独占冒烟仍是官方SDK+pytest512/8257各128输出。首次invalid允许同一候选仅一次-retry1，campaign目录不变；第二次invalid或普通冒烟失败按已有授权停止并回滚184。任何预期不一致先报告、不放量。

本次现场终态：**1 passed、0 skipped，exit0，16.59秒**；仅1个新release服务、2条generation，无invalid/重启/回滚。实际long[512,7745]，完整SHA9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c、usage8257/128/8385，shortSHAfd11a31559daaafb889b8a80f29a412470e0635caae631971a0a31e948a9dfdd、usage512/128/640，均与冻结参考一致。独审从原始SSE重新拼接正文并核对PASS；两条finish均length，backend cached均0，API cached缺失按null记录。

现场首次冷基准文件SHA `df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97`。审批、supervisor/service PID出生、actual argv、active/owner字节一致、GPU锁inode/device/token、source27 SHA及release工作树allowlist均复核；health=ok/serving，backend_epoch=0、restart_attempts=0。冷启动monitor的consecutive_failures持续0，未误报告警。旧exposure.json保留为启动独占阶段历史，当前production_release.json记录 released_internal_endpoint/business_release=true。

2026-10-09T16:14:49.671237+08:00 结束独占并登记放量。使用98304窗口/.88，running/graph2，层优先4096、mamba host0、显式pinned；两个gate原生扩展未改。监控继续运行，未新增实际业务请求或持续时长验收。

原失败部署、Claude诊断、FTD/论文/R067旧轮原件均保留；当前五份文档修订前原字节归档 `release_history/pre_redeploy_smoke_fixed_20261009/`。

R067c和R045没有执行，每次测试停服仍需单独用户批准；push、Strata没有批准或执行。

证据：[审批](redeploy_smoke_fix_20261009/DEPLOYMENT_APPROVAL.json)、[v8独审](redeploy_smoke_fix_20261009/INDEPENDENT_PREFLIGHT_REVIEW.json)、[Linux CPU](release_e2_ops_v2/evidence_v8/receipt.json)、[启动回执](redeploy_smoke_fix_20261009/ACTUAL_START_RECEIPT.json)、[预期参考](redeploy_smoke_fix_20261009/redeploy_expected_reference.json)。

## 封存与回执

新release29文件413052字节快照，manifest SHA `47ca9d497b30d4c0a0ee95789b8cd52651bceff03f833b04c7ca863d88eabed3`；旧184停止后30文件463587字节快照，manifest SHA `7581abd66e9548f628f4cb9881dcdd2aae44a1e68fcf759e1d595f08309b028b`。运行中日志只标记为捕获时点快照，不声称后台永不变化。

[正式发布回执](redeploy_smoke_fix_20261009/PRODUCTION_RELEASE_RECEIPT.json)、[终态独审](redeploy_smoke_fix_20261009/INDEPENDENT_TERMINAL_REVIEW.json)、[新发布证据清单](redeploy_smoke_fix_20261009/DEPLOY-E2-20261009-REDEPLOY-01.EVIDENCE_MANIFEST.json)、[旧184停止证据清单](redeploy_smoke_fix_20261009/ROLLBACK-E2-20261009-COND-01.EVIDENCE_MANIFEST.json)、[历史四条原件离线回放](redeploy_smoke_fix_20261009/HISTORICAL_RAW_REPLAY_V8.json)。
