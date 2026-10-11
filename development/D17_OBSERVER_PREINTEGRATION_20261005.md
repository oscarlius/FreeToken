# D17：D16 批槽观察器预集成

候选：`b9c9248f910e8e2f0560087683e761d436fe8522`，父树 `2396728f5f210b98bfde0b8ba3556e9cbc2b234f`。本地开发后通过 Git bundle 同步专属 `/data2/FreeToken/wt/e2base1`；D14 的 e45 与运行 R035/batch64 的冻结文件保持原样。T17 正式接受前未创建 E2-base.1 标签。

## 改动及实际证据

- D16 的 `0e951a3`、`8994a46` 两个提交分别 cherry-pick 为 `b37b68c`、`b9c9248`。本段增量范围为 D17 父树 `2396728`→`b9c9248`：只增加默认关闭的服务观察器、测试和 README；此增量未修改核心 scheduler/engine/model。完整 D17 相对 D14 的 D06/D07 默认关闭钩子仍须 R041 实测证明等价。
- 观察器读取 native `_schedule_next_batch()` 返回的批次，保存 phase、UID、输入 SHA、table/linear 槽、真实与 padded 大小、active_table_idx 和序号；处理真实 CUDA graph dummy padding，并按预算限定记录数量/字节。观察器出错保留诊断，原方法只执行一次，返回对象保持一致。
- 专属 D17 源绑定 CPU stage `/data2/FreeToken/runs/dev_D16/batch_observer_b9c9248f910e_cpu_e9c18d375c74`：完整 equiv suite **93 PASS，0 skip**，真实 import 指向 D17，CUDA 隐藏，Git 工作树干净。report SHA `b7d53a47f125315a698d90d3fd35b05b9c395fa3187ef4021d0c0e1daac09420`。
- 新 D17 门工装绑定 b9 候选；`/data2/FreeToken/runs/dev_D16/d17_gate_cpu_72db5bbeb92c/source_tools/cpu_validation.json`：**52 PASS，0 skip**，六个实际 CPU 子进程生命周期场景全部成功（success/cold_not_met/warm_not_met/request_error/cold_stop_error/warm_stop_error），封存后结构校验 RC0。report SHA `e655bd545411ceefd0a6e101b85b28d156a76cff78b0d6eb3515823bbc4f8096`。独立泳道 R 已通过 source-startup 范围复核，外部 `/data2/FreeToken/runs/dev_D16/d17_source_review_r_overlap_e655bd545411/review.json` SHA `ea3563d8037cb35dc0beb4532d828d5bcc6ff26e1455a1faca69934d1e806535`；leader 从冻结包实际重核 RC0，`source_execution_ready=true`、`model_admitted=false`。T17 接受、标签、GPU 队列仍为独立前置。

## T20 抽样接线

selector/CLI 通过 SHA 固定的 R041 verifier 重新读取原始证据，记录完整 14 个复核参数；执行前再次重算，封存后的选择发生变化则拒绝执行。缺少/错误证明保留 all28，五目录 diff 只作诊断。

在旧 239 绑定上生成的 reader stage `/data2/FreeToken/runs/dev_D16/t20_r041_reader_cpu_4c63ef7fa7a3` 为 **56 PASS，0 skip**（report SHA `e840cebd9aecd9bd62f9f3fa6dca107acd4cf11cce14723dbf3cc2ff89a36a94`）；真实 canonical D04 和 raw auditor 对已封存 failed_harness clone 的检查正确拒绝验收。它保留为工具回归证据，不能替代 b9 新候选的 GPU 或正向验收链。完整 unmocked sealed accepted-T17/R041 正向 CPU 夹具正在开发，尚未通过。

## 尚未闭合

T17 all28 及其正式独立接受；D16 真实 GPU 批槽对单独运行、缓存/停靠/交错场景；D17 标签、R041 cold+四续算原始测量及独立 D04 kept；T20 实际测量。CPU 工装与模拟数据不授予这些接受。

D16 的“交错”应检测两请求仍存活时 decode→长 prefill→decode 的实际调度事件序列，不以同一个 forward 混相为前提；该混相 scheduler 功能属于后置开发。停靠恢复不能用普通 prefix hit 代替。
