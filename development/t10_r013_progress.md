# T10 R013 阶段 2 进展

2026-10-04 16:09:50 CST 的宿主机观察已确认：`E2-R013 / batch45` 完成 22/22 capture、11/11 成对比较，batch PID 2977969 已退出，无存活测量臂。

独立复核者 `/root/d06_server_review` 随后验证全部 416 个 RUN_MANIFEST 条目、22 个实际 FP32 logits 张量，以及输入、UID、序号、终端 token PID 和张量 SHA。张量实际形状为 `[1,248320]`，全部有限；11 对直接按字节比较一致，top-1 agreement=1、KL=0。冻结比较器的只读重新计算与原有 11 份比较摘要一致。

本轮明确使用“先预热 prefix，再对实际最后一个输入 token 做 K=1 采集”。所有恢复证明为 null。结果证明该场景下成对确定性，不替代 cold full prompt 测试，不证明缓存恢复，也不解释阶段 1 冷热差异的因果来源。

RUN_MANIFEST SHA256：`0aa557c1e9a0571dc6d8ff552f41585ecea09029d3b8ebf1016c8c89c29bf757`。阶段 1 的 R017 封存源和既有失败轮保持不变。

2026-10-04 16:37:57 CST 已完成原始数据及元数据独立复核、D04 封存。元数据父轮纠正为 R017，原元数据逐字节留档，修复源码单独冻结并通过 Linux CPU 7 PASS。历史链、封存清单及只读权限检查通过。

- MANIFEST SHA256：`804d84e9fe0692d2989ba5786cc987599181ff59ecfe687e68b153d49b39cab8`
- round SHA256：`580a24ff8d4009c07fd203eec2660d896922574fae92eadd976ca01c27acbf1c`
- 独立元数据复核 SHA256：`de10719d612984d4e0790ac7aaab74a3fb76ad5e4b61446bd14e689d01be9f3d`
- 正式 verdict：`pending_review`；科学归因和 SC1 条件仍分别待判断。

T04 修复 f506 的新 T16 默认路径门仍待。最新 T16 adapter 29fa24e 和启动器通过本地联合 27 PASS、2 项 Linux 权限检查待服务器执行；旧 adapter 662743c 的 Linux CPU 16 PASS 不替代新版本的 CPU/GPU 证据。
