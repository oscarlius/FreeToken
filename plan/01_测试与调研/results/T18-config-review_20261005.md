# T18 质量输出与思考预算配置核对（2026-10-05）

状态：只读资料核对完成；未测量、未改变运行参数。

## 已锁定配置

- 标准判卷器 SHA：`39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330`。
- 60 题题库 SHA：`bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad`。
- E2-R009 与 Strata 既有 benchmark client 口径：`temperature=0`、`max_tokens=768`、默认思考模板开启；客户端为 `benchmark_client.py phase3`。
- E2-R009 规范重判：47/60，11 题 `TRUNCATED`，2 题 `ANSWER_FAIL`。严格空正文且 `finish_reason=length` 的思考阶段截断包含 `code_05/07/12/13` 四题，另有三道长多轮题。
- Strata 已有结果：52/60，7 题 `TRUNCATED`，1 题 `ANSWER_FAIL`；既有结果说明 7 题均为思考预算耗尽、正文未开始。

## 配置含义与边界

历史证据支持把 768 视为“生成总预算/思考与正文共享的上限”来解释截断；它不能单独证明模型质量下降。E2-R009 与 Strata 只有在相同 client、判卷器、题库、采样参数和预算下才可直接比较；现有结果已核对这些绑定。T18 后续应先盘点逐题 `finish_reason`、思考 token、正文 token、空正文，再提出显式预算对照矩阵，并分别报告 PASS、ANSWER_FAIL、TRUNCATED 与成本。

本轮没有外部文献依赖，也没有对 768 上限作静默扩大；因此不需要 researcher handoff。
