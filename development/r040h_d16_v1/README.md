# R040h：D16 剩余 warm / interleave 验证入口

实际入口为 `runtime/r040h_d16_remaining_prepare_v1.py`，固定候选 `effb9969706922ddad9e59b96377e46469ebe97f`、工作树 `/data2/FreeToken/wt/e2base1-p1`、窗口 98,304、比例 0.88。新测量只包含 warm_0/warm_1 与六个 interleave 服务，共 8 次服务启动、10 次生成调用。

R040g/b113 的四个 parking、两个 cache cold 用例已独立复核并随 failed_harness 轮次封存。入口通过 `R040G_RETAINED_PARTIAL_BINDING_20261008.json`（SHA `49125e61807a4f4c0fa869c4fea78f59789489c2af4d7fe915f8fdc53b43954e`）绑定原提交、round/manifest、独立复核与 15 份元数据，不复制原始测量文件。新 warm 的输入、采样 token、全文和四类状态必须与保留的 cold 对照一致，才写出合并结果。完整 D16 仍需终态独立复算。

修复只涉及测试采集路径：warm 初始化向 native cache 传递 contiguous int32 专家编号。产品提交保持 effb；旧 R040g runtime 和失败证据保持只读。

Linux 包 `/data2/FreeToken/runs/dev_D16/r040h_v1_cpu_20261008_1610` 的 7 项 CPU 测试通过，report SHA `d8ab4968b6a55f832895090430b45a961b20e0160f11e2176a28b11d523c68eb`。覆盖真实 torch warm 初始化、8/10 范围与保留结果合并、失配拒绝和延迟发布。首次文件空跑在服务启动前发现 collector review 元数据错误，已保留失败目录；新 source review v3 通过实际入口校验，源码未改。

实际 FILEdry：`/data2/_shared/runs/ft_rounds/.dryrun_r040h_v3_20261008_1627/dry_run_receipt.json`，SHA `c93ed0fb7dd55e3fcc1e50d24a8edd029caebca5f876721bedd82f1671568c11`。独立启动复核 `/data2/FreeToken/runs/dev_D16/R040h_startup_review_v1/review.json` SHA `bb023e0e2603b26287c6e6e7eac0889919b2bf2361af2f85c6ce1527e74e06d3`，pin SHA `76c1e80f5c9b442d15e4c566aad5e14029222a5af31a0fb9b284ff2512926bb0`。实际入口的 FILEdry 与 startup reader 均接受绑定；全部无 GPU、服务或正式轮次副作用。

GPU 补跑须在实际文件空跑、独立启动复核和用户对这次 8/10 范围的批准齐全后执行。`development/r040h_d16_runtime_prepare_v1.py` 是早期辅助准备工具，不是本轮正式入口。
