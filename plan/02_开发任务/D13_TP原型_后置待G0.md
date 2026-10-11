# D13 TP 原型（**后置**，待 G0）

> 2026-10-08用户已将D13纳入执行范围，旧“后置/待立项”不再是授权阻塞。G0 v3已补逐类设计预算和三负载敏感性；当前执行普通TP2接口/分片设计，随后TP4。实际多卡验收仍需目标节点；现有.9仅观察到一张4090。保留真正TP，未改为层切分。

> **2026-10-05 重新规划更新（优先于下文）**　详见 `../PLAN_20261005_重新规划.md`。

> **按原计划不变**（用户 2026-10-05 决定：多卡保持真正的 TP）。Strata 的层切分只作为论文相关工作与对比，不排开发。仍等四卡到位与 G0。

| 项 | 值 |
|---|---|
| 优先级 | P3（后置） |
| 估计 | 15–30 人日（论文 §10.3、附录 D） |
| 基点 | 立项时指定 |
| 依赖 | **T12（S-002，G0 每卡显存账）** 与总负责人对「四卡怎么组」的决定（用户已定：先做 G0 再定）；**T15（S-005）P2P/NCCL 资料**；多卡硬件就绪 |
| 01 验证 | 立项后建卡 |
| 论文依据 | v3.2 §10.2 估算（TP4 81–100%，未经分配器核实）、§10.3 工程约束、§10.4 G0 与 TP 数值门（**第一阶段不采纳，只列为将来的候选标准**）、顺序「先实现并测量调优后的普通 TP2，再对照新策略，随后扩展 TP4；普通 TP 已能满足业务时，直接承认其效果」 |

## 目标（立项后）

让 `qwen4_exp` 支持 TP2（随后 TP4），先作为**普通 TP 基线**测量，再决定多卡研究问题（§10.3 三种情形）。

## 已知的工程约束与挂点（上游 d3512b4 核实）

| 约束（§10.3） | 挂点 |
|---|---|
| `qwen4_exp` 只支持 TP=1 | `models/qwen4_exp/weight.py:206-207`（`raise NotImplementedError("qwen4_exp weight loading supports TP=1 only")`） |
| `o_proj`、`out_proj` 现为复制，需要行并行 + all-reduce | `models/qwen4_exp/`（立项时读码定位） |
| 超连接、PLE、QSA indexer 的分片未设计 | `models/qwen4_exp/ple.py`（`NGramEmbedding` 407、`PLELayer` 529）等 |
| 离线专家库无 TP 逻辑 | `moe/` |
| 4090 不支持 P2P，NCCL 经主存中转，与专家搬运争同一条 PCIe 与主存带宽 | 待 T15 资料与目标节点实测 |
| 全注意力只有 2 个 KV 头：TP4 时复制 | G0 已计入 |

## 立项时必须写清的验收门（框架）

- TP-n 同配置两次运行逐位一致（§10.4 第 1 项，必须通过）。
- 相对单卡的数值比较采用的标准由总负责人单独评审后决定（§10.4：top-2 logit 差阈值与 60 题只是候选，第一阶段不采纳）。
- G0 结果的逐卡占用要在真实分配器下复核（§10.3「覆盖率不等于收益」：记录实际缺失字节、通信量和图与临时峰值）。

## 风险

高：整模型改造；通信与专家搬运争用；多卡硬件与拓扑未定。

## 交付记录

2026-10-08：隔离分支 `exp/e2d13-dense-tp` 已完成第一段 BF16 dense TP 切分，候选 `f84c49551644544ce37841dd6c99b6dba8dac0da`。QSA/GDN 投影按 head/通道分片，QSA TP4 的 KV 复制分组为 [0,0,1,1]；输出投影使用既有 row-parallel all-reduce；embedding/lm_head 与 shared expert 按现有并行层切片。Indexer、HC、PLE、router、norm 和 shared gate 保持复制。block-FP8 dense TP 明确拒绝。

Linux CPU 检查 `42 passed, 1 skipped`，覆盖实际 reader → dtype materialization → model load_state_dict 的 TP1/2/4 路径、逐语义切片重构、连续内存以及 TP1 回归。证据 `development/D13_DENSE_TP_LINUX_CPU_20261008.json`，log SHA `76176ebcf57db6723c5e1ca9331a5749ae94e8cb1f51f4d11faa237772025e55`。原测试夹具仅验证 key/fusion，并不保证完整模型形状；本次补齐真实模型尺寸后验证，不将夹具修正视作产品数值缺陷。

当前边界：routed NVFP4 expert bank 的 TP>1 guard 仍在，尚无分布式目标模型启动/正确生成/吞吐/分配器验收。下一实现段为 expert-bank TP 分片与相应 all-reduce，随后在用户指定的多卡节点按普通 TP2 → TP4 验收。多卡节点信息待回复，CPU/code 工作继续。

2026-10-08 16:20：独立复核f84c495为scoped PASS_WITH_P2_LIMITS，仅指出conv K/V数值重构断言缺口；e757e3309cc5373c4b6149f02eb86fbb85af9a85已补TP2/TP4的K、V断言，Linux重跑42PASS/1skip，日志SHA02dc5c6b3c96db0e0b18c7eb8106804a2874e1daad0e7b6f3acd6c81b60e001f。NVFP4专家bank TP分片开始实施，实际多卡验证边界不变。

2026-10-08 16:45：候选7e3db7030eb6d4515c19d75fa9a55f43eb6040aa已追加Triton NVFP4专家TP布局与packed/scale/global逐轴切片，保留TP1兼容；Marlin/b12x guard保留。Linux50PASS/1skip，含真实build_expert_banks TP2/TP4重构；log bedb1813f4cb191ddcf74baf393885a792c28862aaa6ddd2cf9918a4e821a35e。独立R报告review_7e3db70_v1.json SHA f6d47b8b83778a94e96e42d59d45d9d984dc4750085b9e44a58a0da5ae0bc63b为PASS_WITH_RUNTIME_LIMITS。实际多rank CUDA/NCCL数值、目标生成、性能及分配器预算验收均未执行；继续核对运行链约束。

2026-10-08T16:59:58.609926+08:00：真实模型overlay config deef67a6 CPU/meta配置预检通过TP1/2/4所有7rank，48offload层、local intermediate640/320/160；矩阵声明794项/每rank。结果development/D13_TARGET_META_20261008.json SHA5e75b847c4943abbb157a303a7fa456d4c144202fd113198dac004e0078ae35a。该预检只验证目标配置下模块声明，未读取权重、运行collective或验证输出，不当作实际显存/性能证据。
