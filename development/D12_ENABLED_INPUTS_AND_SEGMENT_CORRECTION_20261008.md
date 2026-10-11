# D12 启用验证：分段口径与冻结输入

2026-10-08 17:16。此记录是离线输入准备，不是 GPU 准入或验收结果。原 T06 请求级分析文件与封存轮次保持不变。

## 阈值口径修正

候选 `8f6a912ea6066f192c37dc74435efc9da0c7591c` 的 `layers/moe.py::_prefill_routed` 以 `hidden_states.shape[0]` 与阈值比较。因此，实际单位是**单次 MoE forward 的预填段 token 数**，不是一条业务请求的全部未缓存后缀。anchor 切分可使一条较长后缀包含多个命中阈值的小段。原开发卡和 CLI 中的“actual suffix length”不够准确；本提案统一使用分段口径。固定候选未因此改动，R062 默认关闭门仍绑定原提交；CLI 文字修正纳入后续集成待办。

对 E2-R046g 三组 ordinary-worker 的原始绑定、最终 D0 行和 route JSON 做离线复算，196 个输入文件逐项匹配封存 SHA。`G_two` 仍不进入本分母。

| 口径 | warm 总数 | 长度 ≤256 | 说明 |
|---|---:|---:|---|
| 完整请求后缀 | 29 请求 | 10 请求 | 原统计数值正确，但不是代码分支的判定单位 |
| T06 route tracing 下的 MoE forward 预填段 | 51 段 | 35 段 | 长度单位与分支一致，分母仅属于该历史采集配置 |
| 至少包含一个 ≤256 段的请求 | 29 请求 | 27 请求 | 只表示潜在命中；仍须满足 GPU offload、pinned、no-overlap 等条件 |

真实段中 `n=64` 有15段；`1/19/32/256/257` 均没有观察到。不能继续把“没有≤64请求”写成“没有64段”。阈值256保留为预先提出的探索值，并非最优或发布设置；35/51也不构成性能收益结论。

进一步源码约束：`engine.forward_batch`在route tracing开启时不进入layer-major；关闭tracing后的候选可能把长段再分为4096-token内部子段，D12实际判断这些子段的hidden_states长度。因此51段不能当新候选的预测分母；新诊断须绑定实际D0`subchunks`和MoE child上下文。所选历史64/233/123短段低于4096，仍须在新执行中核实。

## 最小普通请求历史

按 G_seed12k 的历史顺序固定前三条完整 payload，保留原字节、tools、temperature=0、max_tokens=2048 和普通 SSE 协议。下一请求使用封存 payload，不以新生成的答案拼装下一请求。两臂使用同一候选，均 `--disable-moe-prefill-overlap`，阈值分别为0和256。

| 原 round | prompt token | 原缓存 token | 历史预填段 | 用途 |
|---|---:|---:|---|---|
| 0 | 12660 | D0=0；API未报告 | 512、12148 | 冷启动和长段回退 |
| 1 | 12905 | 12608 | 64、233 | anchor 分段和两段阈值命中 |
| 2 | 12987 | 12864 | 123 | 单段真实短后缀 |

历史段形状是新重放的待验证预期，不能直接当作新候选的观测。实际运行必须重新绑定 worker input IDs、UID、segment 序列、开关路径和完整生成输出；任一输入/分段不同均不能沿用本表宣称覆盖。普通服务启动、实际 MoE 分支、CUDA 搬运、状态/logits 和输出均尚未验证。

三份小型 prefill route NPZ 已逐项校验封存 SHA，按48层各自的原始专家号去重；未使用 decode 的专家并集代替 prefill：

| 历史段 | 唯一专家数最小值 | 层中位数 | 最大值 |
|---|---:|---:|---:|
| round1 / 64 | 88 | 143.5 | 221 |
| round1 / 233 | 146 | 237 | 329 |
| round2 / 123 | 134 | 227 | 311 |

这只描述历史路由适用面。唯一专家数不等于 cache miss 数、H2D 字节或节省时间，且不能代表未分析的其他32个短段。

## 工具与证据

- 本地工具：`development/d12_enabled_inputs_v1.py`，只读封存输入并创建新的派生目录；没有服务、GPU、HTTP、锁或正式轮次操作。
- 本地输入：`development/d12_enabled_inputs_20261008/`，包括三条 byte-identical payload、对应 worker token IDs、原 binding 和汇总 `binding.json`。
- 远端派生：`/data2/FreeToken/runs/dev_D12/enabled_inputs_v2_20261008_1715/inputs/binding.json`，SHA `282ec437c54b0ba341aac5a0bc31e996ca0d53343d0f48d5b8fa488523ca00e2`。
- Windows/Linux 均8个定向校验通过；Linux report SHA `be23dfed8fc15163788f6611006027bedf08d8f08838c8482c4ba196226f7a96`，本地副本 `development/D12_ENABLED_INPUTS_CPU_20261008.json`。
- 独立复算通过：`/data2/FreeToken/runs/dev_D12/reviews/enabled_inputs_v2_review.json`，SHA `3aca4421b3ee1e9455a61bea0fbf38ea4f15bd35017d1fe0ced253df36b5fdd3`；本地复核摘要 `development/D12_ENABLED_INPUTS_REVIEW_20261008.json`（独立摘要schema，非远端逐字节副本）。
- 原 round SHA `3f50a0ffb69e24e65eb10df1b925ed9bbf75c74e51ddd385f05369947134f54d`，MANIFEST SHA `282f1a046a33d46345c9b3f72630a2f0971c3d4f92839c2e0d6f100e6232c9f1`。
- 初次离线派生在处理冷请求缺失 API cached 字段时失败，未写入输入结果；原 `enabled_inputs_v1_20261008_1713` 工装和失败日志已保留只读。修正只允许冷首请求以绑定 D0=0核实，缺失 warm 字段仍拒绝。

## 剩余准入工作

先等待 R062 默认关闭门的具体执行批准并真实验收；另行完成启用功能 proposal 的四层判据和工装接线，复用 D03/D16 的存储传输、续算状态、固定 token logits 与端到端输出检查。独立控制臂的标定方法沿用 D03/T04；没有同输入可用 envelope 时明确补齐，不从 D12 自身误差生成容差。性能臂在功能门通过后执行，统计观测臂与性能臂分开。

本记录不分配新数字轮次、不新增 GPU 服务或调用授权，也不关闭边界样本、真实 CUDA 和性能缺口。

2026-10-08 20:00 参数勘误：以上关闭 overlap 的命令已按候选 args.py 与真实 CLI help 改为 `--disable-moe-prefill-overlap`。旧分析 JSON、旧源包 README 和已固定轮次保持原始证据字节；其中 `--no-moe-prefill-overlap` 是历史误写，不能用于启动。此改动不改变两臂 no-overlap 的实验设计。
