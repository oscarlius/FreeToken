# E2 发布门证据审计（已关闭；FTD已发布，v5独立终审PASS）

## 1. 门状态与候选边界

根门已闭合，权威本地记录为 [E2_RELEASE_GATE_CLOSURE_20261009_v2.json](E2_RELEASE_GATE_CLOSURE_20261009_v2.json)，SHA-256 `7c2309bd1591bfe57163e7fcb1d2a5e2d3d504230a20fcb9c11f8f602f5ae006`。候选 `481d3a7` 由 `0aa23431 → 4c878f6 → d577e32 → 481d3a7` 的提交链组成。回滚仍为 `184c965`，历史普通 8192 分块、49152 窗口。R063a 是 E3 D12 default-off 的 kept 结果，不是 release gate。

## 2. 四类闭合证据

1. **冷路径。** 三条 8257-token、绑定 SHA 的 cold reference 由 closure 固定；范围只是相同绑定提示与服务隔离，不是 temperature=0 的通用确定性。
2. **T17 同结构。** E2-R038 的 retained 14 + new 14 = 28/28 对已测尾段 65、4095、4096、4097、8191、8192、8193，比较四类状态、token 与全文；不覆盖所有 ≥65，≤64 未证明。
3. **并发 canary。** R066b 的 shared/independent-prefix canary 被保留；它不建立物理 batch 或任意并发正确性。
4. **R066c 分类 c。** 3 services / 5 requests 全部 grammar anomaly；冷路径也异常，因此分类 c 只在该判别范围内成立，没有额外 crosstalk 观察。R066c 不证明任务完成、普适无串扰或机制因果。

## 3. R066c 原始结果表

API `cached_tokens` 缺失时记为 `null`，与后端 cache=0 分开；热路径为 API/backend 8256 + 30。五条均完成 `completion_tokens=32`，usage 已逐条核验。前三行保留原始前 3 行及首行空格。

| service | prompt | cold/hot | backend cached/new | first three raw lines | grammar | full text SHA-256 |
|---|---|---|---|---|---|---|
| X | SUNSTONE | cold | 0 / 8284 | ` SUNSTONE-7319` / `CODE: SUNSTONE-7319` / `CODE: SUNSTONE` | anomalous | `95985eee904b14371c3841a138d8c4a1f500e3a63fcdd7b030c1fa1e96b5a1f2` |
| X | GLACIER | hot | 8256 / 30 | ` GLACION-4826` / `CODE: GLACIER-4826` / `CODE: GLACIER-4826` | anomalous | `c4fe6f779240ed9d05a57ee7ae6a4fd1f85aa48e46621a4e2641637e405cca70` |
| Y | GLACIER | cold | 0 / 8286 | ` GLACION-4826` / `CODE: GLACIER-4826` / `CODE: GLACIER-4826` | anomalous | `c4fe6f779240ed9d05a57ee7ae6a4fd1f85aa48e46621a4e2641637e405cca70` |
| Z | SUNSTONE | cold | 0 / 8284 | ` SUNSTONE-7319` / `CODE: SUNSTONE-7319` / `CODE: SUNSTONE-<think>` | anomalous | `21d96a10b4bde73b5c138116baa42a24841f160a7d6b44abbdad42b4a5c143cc` |
| Z | GLACIER | hot | 8256 / 30 | ` GLACION-4826` / `CODE: GLACIER-4826` / `CODE: GLACIER-4826` | anomalous | `c4fe6f779240ed9d05a57ee7ae6a4fd1f85aa48e46621a4e2641637e405cca70` |

X warm, Y cold, and Z warm GLACIER share `c4fe…`; Z 的两个 full SHA 与 R066b primary first-pair 的旧 SHA 对照仅是 observation，不能升级为新判据。每提示 0/a/b 都未满足：SUNSTONE cold 异常且 GLACIER standalone 均异常。未观察到 other full marker、U+FFFD 或非法控制字符。

## 4. 封存、运行与限制

R066c round SHA `b29c09c71943902809c261f348628495ca5213aab0977486a9630d9fe59a8e08`，manifest SHA `71bce2d83055cde9660fae683832b509792f54b980a8e59cb0683ba90784e337`，pin SHA `cbbf8fbc41af6a7b30bae98c843f7d11358aee73b996b9b8e0e6a372bd0c5a0d`。启动前冻结自检为 local 76 / Linux 101（含 legacy `false,false,true,true`），测量后 GPU process、端口与锁均清理，50 原件未变。

生产配置仍为 98304/.88、running=2；R066 私有配置的 running=4 不得外推。≤64 正确性待证。保留的 T20 `failed_harness` 仍为失败；旧 `not_met`/`failed_harness` 机器判词不追改。

## 5. 已完成交付与待批准操作

`data_release_published=true`。FTD manifest已只读发布，论文v5最终构建及独立复核已完成。分支创建、部署、推送分别待批准，均未执行；Strata22服务/345调用仍未批准。


## 新FTD与论文交付绑定

[FTD-20261009-1](../plan/data_releases/FTD-20261009-1.json)已在服务器只读发布，本地逐字节相同；manifest SHA256 cff4e114ba6f661878a601f353756dc0367d478dda487787e32f8ec64cd95840。23个正式轮次+R036许可沿用引用，旧FTD03/04/erratum、原判和hypothesis边界不变。

[论文v5](../paper/FreeToken_MultiGPU_CoExec_v5.0.html)由src构建，HTML SHA256 2e2b3c726b94107dde542f091ee0a31c694b5c3ccf6f73aa7d1504e71cadfa0d。11图18表，桌面/窄屏通过；[完整原文表](../plan/01_测试与调研/results/T20-E2-R066c_20261009.md)记录R066c五条回复和Z逐条SHA比较。


最终独立复核已封存 **数据 PASS / 论文 PASS**：[FTD-20261009-1_AND_PAPER_V5_REVIEW_20261009_v1.json](FTD-20261009-1_AND_PAPER_V5_REVIEW_20261009_v1.json)，SHA256 `16bea91f531c1fc65805578f405aa1acb020b37c2826c5cc3f34a4e2ba380ba3`，远端0444、本地同字节只读。浏览器验证使用[最终v3回执](paper_v5_validation_20261009_v3/render_validation.json)；独立R复核该回执及绑定，未另行运行浏览器。复核通过仅适用于数据和论文交付，不授予建分支、部署或推送权限。
