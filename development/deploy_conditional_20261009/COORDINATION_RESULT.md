

## 2026-10-09T15:29:31.155208+08:00 条件发布失败与回滚恢复

本次条件发布 `DEPLOY-E2-20261009-COND-01` 达到 serving 后，独占SDK/pytest冒烟 **1 failed、0 skipped（exit1）**：8257提示的Prefill日志为512+7745两行，固定4096断言要求3行。候选未放量、无已签冷基准，已完整停止；按已有授权 `ROLLBACK-E2-20261009-COND-01` **恢复184c965，health=serving、回滚冒烟1 passed/0 skipped（exit0）**。当前49152窗口/普通8192、running/graph2，supervisor2887078/service2887095与GPU锁身份已核实；回滚自己的SHA/usage基准已保存。推送、R067c、R045和Strata均未执行。完整结果见[部署结果](../development/DEPLOY_RESULT_20261009.md)。

失败证据27文件manifest SHA b3dbd266b4ae87d57a9f8713cd0c5a9d19e9f3199d48e87209e39f779ae3655c；rollback首次基准SHA 4cf527c0445c5540b2259904864250f50ec1ba1c25ed8567bbbfd6ac6934d3de。本次release预期3日志行、实际2，未出现exit75；未改判据重跑。STOP已证资源完全释放后才启动rollback。实际根协调记录同时写入服务器 /data2/FreeToken/runs/production/coordination.jsonl。
