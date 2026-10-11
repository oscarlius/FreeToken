# R049a GPU补跑审批包

结论：工装就绪；尚无GPU补跑批准。独立R启动复核与root实际入口admission回读均通过，真实核验时间2026-10-08 01:29。

范围：T21原九服务 L1/P1/PA1/L2/P2/PA2/L_D0/P_D0/PA_D0。R049/b101合格完整臂为0；新服务/缓存完整重测L1五个工作负载及后续原范围，前四项只保留diagnostic原件，不跨轮拼性能。候选988c9e183c8dca4415fd9b5d02318b26664da619，父effb996，窗口98,304、比例0.88。训练只seed12k，冷32K、seed_45k（实际约12K）、seed_real触窗自然止、两路为留出/测量。性能不开D0/trace/暂停，D0另开诊断服务。

修复：只在two_decode固定512的请求显式ignore_eos=true/max_tokens=512/no stop，exact512和length判据保留；其他冷/会话参数不变。实际候选API→GenSpec→TokenizeMsg与Scheduler EOS/length CPU链通过；新异常路径如实记录failed_harness和owned_cleanup，原异常仍抛。新入口严格绑定failed b101 D04 round/MANIFEST/pin/receipt、只读与history，并禁止复用partial性能。

证据：Linux32PASS；same-entry九服务FILEdry无服务/请求/锁/batch；独立R与root回读。
CPU报告 /data2/FreeToken/runs/dev_T21/r049a_v9_cpu_20261008_020000/cpu_report.json
CPU SHA 5fd2e42e41237347199cd1dbf808af3653d3985aa3dc1b0a47ed10338e11355b
FILEdry /data2/_shared/runs/ft_rounds/.filedry_E2-R049a_v9_sourceclosure_r2/dry_run_receipt.json
FILEdry SHA 6867980e3c0891c9e66714cbd86eb97f1081b731f80fc2b735c9ffdbb4d1355d

批准后GPU空闲即可按串行队列启动；当前未创建正式R049a轮次目录。HANDOFF §8第4条/§13第7条要求已有服务或完成臂之后失败的GPU重试需用户裁定；此次修的是工装，不改产品/verdict/512判据。

准确启动绑定：

- entry_path: /data2/FreeToken/runs/dev_T21/r049a_v9_cpu_20261008_020000/source/r049_t21_ordinary_prepare_v9.py
- entry_sha256: e161375719cce4ce85358d781baa55d384b2b6fb25504798179952d34f34f48e
- review: /data2/FreeToken/runs/dev_T21/E2-R049a_startup_review_v9.json
- review_sha256: 31697989b900fdd931de5c621174c196b9a553280e331338276e6625a16d97e0
- pin: /data2/FreeToken/runs/dev_T21/E2-R049a_startup_pin_v9.json
- pin_sha256: 686d1cb305cdfd363d62f6d554a7e419259b32823540e4164712b19381cfd849
