# R049b 剩余八服务重试审批包

准备完成时间：2026-10-08 05:47（服务器 date 实际输出）。

## 本次范围与保留项

申请 E2-R049b，仅补 T21 未完成的八服务：P1、PA1、L2、P2、PA2、L_D0、P_D0、PA_D0。候选仍为 988c9e183c8dca4415fd9b5d02318b26664da619，发布配置 98,304 / 0.88；性能臂保持生产口径，诊断臂单列。

R049a/b102 在 L1 已完成之后，因输出 schema v9 与校验器口径不一致失败，原轮次已 D04 failed_harness 封存。独立 R 原始复算证明 L1 的 24 个请求（两冷、seed_45k 十二、seed_real 八、两路各 512 token）可保留；不重跑、不复制原始文件、不改变旧 verdict，也不据此单独宣称 T21 提速通过。

保留复算：/data2/FreeToken/runs/dev_T21/reviews/E2-R049a_L1_recompute_v1/review.json，SHA 736e8cb50fe93dba781e371ca5d937eb55fa212cd83c2281b522654044d32b06。
旧封存 round.json SHA 6b0fd937bb2095d734b8d74b66ffb01d508933052ea40af221a95238e4f87337；MANIFEST SHA 34e1f6b58139fda67504b9a35921fd50592af79e24691314c2644aaecdaa2191。

## 新工装及验证

v13 同时修正实际 schema 校验、正式 driver 的保留 L1 装载、冷请求沿用 E2-R049a-cold1/cold2 输入标识，以及 child 成功返回时释放自有 GPU 锁。冷输入逐位、输出 512 token、收益判据和 SHA 绑定均未放宽。成功锁释放修复先取得失败回归，再取得通过结果。

本地 50 PASS / 6 Linux 跳过；Linux 完整入口 CPU 56 PASS。测试隔离 CUDA，启用 socket guard，未占 GPU、未访问模型端口。
冻结目录：/data2/FreeToken/runs/dev_T21/r049b_v13_root_cpu_20261008_054143。
入口：source/r049_t21_ordinary_prepare_v13.py，SHA c19fe3f66b7247122f75800387e9224316e0bd2c251d16370ef6b45c7c51db74。
CPU report.json SHA a2c67805466786d31e53d2d7ca0d1769116623831aaef4a93ca7b1bfd8b791b7。
source_manifest.sha256 SHA 535835b8eef0a3d7526d2b2bf74a0240ed734f0eb21705a437b9f83e535bf584。

同一服务器、用户、路径、入口的真实路径空跑已通过：
/data2/_shared/runs/ft_rounds/.filedry_E2-R049b_v13_retained_l1_r1/dry_run_receipt.json，
SHA fadeb6275807f54ec49508808efef203e893dd23f6b3ec0405cf72534c7f5d83。
回执确认未创建正式轮次、未起服务、未发请求、未拿 GPU 锁、未分配 batch。

独立 R 启动复核 PASS：
/data2/FreeToken/runs/dev_T21/E2-R049b_startup_review_v13.json，
SHA ad3755827e7a3a5983017702c3959373e6387194c6a0ff321da59516b3d3f299。
pin：/data2/FreeToken/runs/dev_T21/E2-R049b_startup_pin_v13.json，
SHA 49e1841f58d07dc9396d0e663f377618670ad0345e25841a128d2b4f862f7259。
两文件均 0444；R 实际调用 require_review(dry) 通过，未执行 admission 或 GPU 操作。

## 执行边界

依据 CODEX_HANDOFF_20261006.md 第八节第 4 条和第十三节第 7 条，测量后失败的 GPU 重试须用户批准。原 R049a 的批准已执行，不扩展为 R049b。

用户批准后，仍等当前 R040e/b104 正常完成、复核和封存，并在拿锁前重新核验当前清单、SHA、只读权限、D04 history 和自有锁边界；不重读旧原始数据，不抢占正在运行的批次。整轮结合保留 L1 和新八服务复算后才给 T21 判定。若 not_met 或测量后失败，保留证据并停止该分支。

