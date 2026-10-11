# E2-R046g：仅补 G4/T06 审批包

R046f/b98测量后工装失败，已D04 failed_harness封存。G3沿用R046e两臂，旧原始/verdict不改。新版仍仅补G4/T06四个普通会话服务。

修复：r046c_ordinary_seed_driver_v3.py采用持久化sort_keys顺序及实际API规范化后再由候选分词器规划。12,660实际worker IDs逐位一致，输入SHA约束保持。Linux49项通过（含实际候选分词、已封存worker比较）；原CPU回执rid元数据写错，已另出更正版并保留原版。同入口/路径/用户真实FILEdry四scope通过，无服务/请求/锁/正式轮。独立R启动PASS，root正式require_startup_review()回读PASS。

配置：候选4fc2320dc0a29422ab61e383e5e1579460e9926e，98,304/0.88，暂停关闭，普通overlap显式开启；G3不重跑，GPU严格串行。

入口 /data2/FreeToken/development/r046g_d07_t06_prepare_v1.py
SHA fd23a3b409d872411df3cff9bcc8580451a7d4f4dd55c297c7e09acfa27a34d1
driver SHA 00e31fcb664492f835046bd05eb832ba8f2914ad74a01ab640a6a64c3f40031c
CPU /data2/FreeToken/runs/dev_R046/r046g_cpu_corrected_v2_20261007_231726/report.json
SHA e2ecbe56b736d9f01b825a10993889a0c852e39a131125506f1023f97e85b103
FILEdry /data2/_shared/runs/ft_rounds/.filedry_E2-R046g/dry_run_receipt.json
SHA 6d45b6a4fb1d7132f16b0a1cea773506204ef14aa5bffebfe08d792bcec8774f
R review /data2/FreeToken/runs/dev_R046/reviews/E2-R046g-v1/review.json
SHA 546ce33ff4e34abc9dc0e7562363af0c5d30a3f014cd2a0b4783c6f341d65820
R pin SHA 6cc0d2ca13e77b06a6903a103c9fdc6019b7ce19772f71dda97a7c8f53f6a0d2

启动前前置只查清单/round SHA、只读位、D04 history。HANDOFF §8.4 / §13.7要求测量开始后失败的重试需用户批准；R046f批准已执行，R046g尚未授权。批准且锁空闲预计5分钟内启动。无release/e2、部署或推送。

用户23:28已批准仅补G4/T06，batch99已启动并核验child/本轮锁；批准回执SHA18e29d4b475784933da3afc89329505bd50197db9f5b6b7174d3c144f712af22。上述未授权描述为审批前历史状态，当前运行态见README/FTD/协调日志。
