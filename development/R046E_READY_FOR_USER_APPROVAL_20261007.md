# R046e G3/G4 与 T06 补跑审批包

准备完成时间：2026-10-07 21:36。独立 R 只签启动准备，不替代用户对测量后失败重试的批准。

补跑范围：D07 G3 trace 开/关（暂停均关闭）、G4 以及 T06 四臂。全臂窗口 98,304、比例 0.88；候选 `4fc2320dc0a29422ab61e383e5e1579460e9926e`。同配置重跑 G3-off；R046d 原件及其历史 G3-off 保持封存。T06 只以 seed12k 训练画像，seed_45k、seed_real、两路为留出；seed_real 不截短，触窗记录完成轮数。

前置 R062/b93 已独立复算并 D04 kept，90 文件、7 目录只读；默认路径四臂全文、prefill 序列、13 段 D0 H2D/D2D 以及多消息参照一致。R046e 真实追踪业务尚未测量。

| 启动证据 | 服务器路径 / SHA256 |
|---|---|
| 实际完整入口 | `/data2/FreeToken/development/r046e_d07_t06_prepare_v2.py` / `ca058ee105d3cdbbd15345e64257f662aa70c5db4e580e57859a2fa99b17d731` |
| Linux 源隔离 CPU 21 PASS | `/data2/FreeToken/runs/dev_R046/r046e_v2_source_cpu_20261007_213146/report.json` / `4c0c1c798d0d1d594a89d4e4de93b4e48b1855e6b751419f573e6fe727df702d` |
| 同入口、路径、uid1000 六 scope FILEdry | `/data2/_shared/runs/ft_rounds/.filedry_E2-R046e/dry_run_receipt.json` / `9659ee0e234dba6bb019fe090641e99b2445696a4e726971f23ee21150b2a460` |
| 独立 R 启动复核 | `/data2/FreeToken/runs/dev_R046/reviews/E2-R046e-v2/review.json` / `670be09f9321a9ba2286821cf70c2cac2454afeb4df9f9c1069711e89ae22946` |
| R pin | `/data2/FreeToken/runs/dev_R046/reviews/E2-R046e-v2/pin.json` / `ecbf5e1da699629fbdfdfa71d7c38f8c164d720715992936c95e0dc087e2bd2d` |

实际 `require_startup_review()` 已回读通过。FILEdry 无模型服务、无请求、无 GPU 锁、无正式轮次目录；冻结源与签字只读。R核验 G3 唯一变量为 trace 开关，前置只查清单、round SHA、只读位与 D04 history。

批准后可在 GPU 空闲时立即启动；运行中独立逐组复算，完成后 D04。发生 not_met 或规定内测量后失败仍按交接书停问。此批准不包含 release/e2、生产部署或远端推送。
