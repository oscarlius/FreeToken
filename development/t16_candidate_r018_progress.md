# f506 候选 T16 默认路径门

主线负责人维护。2026-10-04，D03 普通分块诊断传播修复候选 f5067bbe05da51d5f78185213435a8be095a684a，直接父提交 c30ae0d7003c3bbbf56867ce74da797332fa7ed5。

新适配器准确 Linux CPU 29 PASS，最终启动器单独冻结后准确 Linux CPU 32 PASS（含真实进程组清理与权限回归），原协议自检 PASS；最终源码和 Linux 证据均由独立复核者检查通过。旧源及 CPU 记录保持不变。

- adapter SHA256：29fa24ed89a3e35ddd0c426c67fa9c481f85d1700a5498a7c0abc8daab01e0c6
- final launcher SHA256：241cbccc21ee34fe61e64af48530117b8cf243b979ad1d577563f77d2bee0d0e
- final Linux CPU log SHA256：58620a3490ddf3cb7091b8f0f6c4a1913b112845365ee8eb92b0b189fb15437d
- final Linux CPU report：development/t16_launcher_cpu_241cbcc.json

实际新启动 E2-R018-gate-D03 / batch46，batch PID/PGID 3451139，启动回执 development/t16_candidate_r018_launch_receipt.json，SHA256 49a2fa4327613d639413e57a0d66115f3c0033c7508f91db8c97b3ffa1dba88b。启动前服务器 GPU 为4MiB，8095空闲，无GPU锁；父树和候选完整提交、实际导入来源、编译扩展、固定工具源预检通过。执行的是受保护只读私有源副本，包装脚本和回执采用独占预约。

该轮共8臂：层优先四臂与普通分块四臂，父树/候选各D0开关对照，普通分块包含2000及32052 token。当前阶段及真实摘要计数以看板 observed_at 或 status_batch46.json 为准；启动和加载不是测量通过。测量完成后仍需独立复核、D04封存和正式判定。T04真实12672恢复的验证尚待此门后执行。

## 测量、复核与封存结果

2026-10-04 17:45:55 CST测量结束；8臂均完成。层优先13条、普通分块23条完整D0事件与scheduler事件对应，D02尾段完整；参数仅PID差异，业务prefill序列、H2D/D2D计数相同。D0/PROD各自的层优先、普通短输入和普通长输入共6对生成全文逐字节相同，均实际生成128 token。first-shot单列，不构成性能验收。

冻结归档源码外部重放报告 `t16_r018_replay_3a5e987_cpu.json` 已重新计算并匹配原gate；独立原始数据与元数据复核通过。封存工具固定canonical原轮次、完整独立review bytes和实际D04版本；Linux11PASS及私人副本实际D04流水线通过后，经独立复核再封存真实轮次。

实际关闭时间：2026-10-04 18:33:15 CST。正式verdict仍为pending_review，parent为E2-R002-gate-D03。真实proof见 `t16_r018_actual_closure_proof.json`（fixture_override=false）：

- gate SHA256：cfdd3a08f4af422178fdd72f058ea67783002fd0a506ca3388acaaae64b9b566
- 首次封存v001 SHA256：99517fb399c8adf758e2b50a63bedabf7b5c5fb322d8795c2e4fc0d33a940ca7
- MANIFEST SHA256：e7b63c0ec3c4b2d53d42663581af9bcd86de21dd3cf9748fc450c3b19b80f142
- 独立raw review SHA256：6c2a90d98c028ceaeff90d78a85e6eb75b368982a3114f2b6eed1524ea787243

封存后独立校验全部清单、历史逐字节一致及只读权限通过。G4/G5开发GPU自检已结束并独立复核通过：七个边界齐全，G5两新进程64/64位置逐位相同。G4的74点开发比较没有合法包络（legal_pairs=0），不构成T04科学验收。T04真实12672恢复仍待。

计划要求的E2基线版本标签在首次元数据中遗漏，已经D04追加到v002：当前round SHA256 `36c249835233e9bdf2d09e7825fef7c377220f0f8006d99264f2b2b77e71b5f7`，code_version=E2-base@23f2e2c。base.commit仍为实际父树c30；v001、MANIFEST、测量值及verdict保持原值。独立复核见 `d03_f506_r018_independent_review.json`。
