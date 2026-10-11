# E2-R040b：启动审批包

准备完成：2026-10-07 21:00，独立 R 已签工装准备 PASS；该签不授予 GPU 补跑。

申请仅补 R040a 未完成的 D16 双批槽、四批槽、停靠、缓存、交错，共 30 次服务启动。保留 R040a 六个已完成锚点，不重跑，不修改其 failed_harness 封存。

发布树仍为 0aa23431e5b800797543bdecbf35a01045131d7d，98,304 / 0.88。修复仅在新观察器与工装版本中：在实际 Engine.forward_batch、input_ids 完成赋值后的边界捕获真实几何数据。产品树未改。

- 实际 17-role CPU 全导入、normal-spawn、真实 Scheduler._forward 边界回归 4 PASS。
- 实际正式 controller/child 入口隔离 Linux 5 PASS。
- canonical collector 17-role source review PASS，SHA 31f1fb77a519b92d3cf64ce749557c1b972c91105ae3fabffc225d8cc67af85b。
- 服务器同入口、同路径、同用户真实 FILEDRY 通过：/data2/_shared/runs/ft_rounds/.dryrun_R040b_20261007_205310/dry_run_receipt.json，SHA 1a076d15e2163fb01f8c4e010fddaab17658e5cabb486eb859c3dbf6056a8658。执行全部 30 项文件操作，未启模型、未取 GPU 锁、未创建正式轮次。
- 独立启动准备 review：/data2/FreeToken/runs/dev_D16/r040b_startup_review_v3/review.json，SHA 2f45019bc058691cdf3cc2bd4a3ecd8e5b9b4f3760637310ffc8020058e5f70c。
- pin SHA 0fd4c6be013df5335e51461d1925a455dce03db778b00e11c3b54c026aca5dcc。review/pin 444、目录 555。
- v9 实际 require_startup_review() 已回读通过，48 来源/清单、FILEDRY、seed 元数据、R040a round/MANIFEST/D04/六锚点绑定一致。

实际入口：/data2/FreeToken/runs/dev_D16/r040b_v9_source_capsule_20261007_202812/source_tools/r040b_d16_remaining_prepare_v9.py。

若获批准，在当前运行批次结束及 D04 封存后，按已授权的“已就绪且无依赖批次先跑”规则排队，不抢占当前 R062，不部署或推送。若测量后再次失败，仍停下报告首项并提出解决方案。

必须询问依据：交接书第八节第 4 条及第十三节第 7 条要求测量开始后失败的 GPU 重试由用户裁定；R040a 已完成六臂后失败，因此该次补跑不适用零服务阶段自行重试。
