# 2026-10-09 冒烟修复后重新部署指令

用户先要求读取Claude诊断、重新冻结OPS、Linux FT venv CPU全套0 skipped及独立审查；随后明确已有条件预批，无需再次确认：两条件满足即停止184c965→启动481d3a7→独占冒烟。

预期long行结构[512,7745]，正文SHA9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c；不一致报告且不放量。冒烟失败或同候选第二次smoke_invalid按手册回滚184c965。R067c/R045每次停服另报批；push/Strata未批。

OPSv7冻结24源码、Linux58 passed/0 skipped，但独审BLOCK：首次预期参考与一次invalid重试上限未在入口强制。旧包保留不改。v8补强后27源码、local/Linux各65 passed/0 skipped及独审PASS；其source_manifest SHA029add4d8ca253ae64a8a34350f2287ab9e72acd631f049cc362d7e4921d5429。产品481及两个gate原生扩展未改。

本次已有授权编号：DEPLOY-E2-20261009-REDEPLOY-01，停止旧服务STOP184-E2-20261009-REDEPLOY-01，失败停止STOP481-E2-20261009-REDEPLOY-01，失败回滚ROLLBACK-E2-20261009-REDEPLOY-01。仅一次invalid重启的服务/run审批号为DEPLOY-E2-20261009-REDEPLOY-01-retry1，原campaign目录保持不变。编号用于绑定本次已有授权，不授予其它停服/测试权。

原始DEPLOY-E2-20261009-COND-01仍为exit1失败；其27原始文件、回滚首次冷基准、Claude诊断及旧文档归档保留。新版离线回放通过不会改签旧失败。
