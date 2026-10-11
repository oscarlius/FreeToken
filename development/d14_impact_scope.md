# D14：绝对位置错误的实际计算影响

绝对位置错误会改变真实 GDN 和 PLE 初始状态。影响不限于快照计划和日志。

在 E2-base 的层优先长续算中，调度器先恢复前缀的 linear-state 槽，再进入 model forward。旧 Engine 为首个子请求设置相对 `cached_len=0`，FLA metadata 据此把它标为 fresh。模型因而能忽略或重置已经恢复的状态：

| 实际调用链 | 运算效果 |
|---|---|
| `attention/linear.py` 用 `cached_len > 0` 生成 `has_initial_state` | 原本有前缀的首个子块被误标为无初始状态 |
| `models/qwen4_exp/gdn.py` 的 conv 调用使用该标记 | 恢复的 GDN conv history 不按有初始状态路径消费 |
| 同文件以 fresh slots 对 `recurrent_states` 执行 `index_fill_(..., 0)` | 恢复的 GDN recurrent 状态被清零 |
| `models/qwen4_exp/ple.py` 使用 `fresh=~has_initial_state` 和 `torch.where(fresh, EOS, context)` | 恢复的 n-gram context 被替换为起始上下文，PLE conv 也走 fresh 路径 |

本结论来自直接父树 `23f2e2caa3395837c9474735ffc83321f3b9b5a1` 与候选 `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42` 的实际源码调用链。D14 保留子请求的绝对缓存位置，并投影一次冻结的原请求快照计划；CPU 13 项修复前失败、修复后通过。

位置错误的直接触发条件是**有缓存前缀且剩余预填进入层优先分块执行**，包括超过 4096 预填预算的长续算。65-token 短后缀本身不进入这条长续算分块路径；但它仍可能消费由另一项快照计划错误写出的 donor，故短后缀也需实测。快照错误另影响冷层优先预填所捐赠状态的 n-gram 身份，不等于其当次冷输出已被证明错误。

目前已核实旧 RLM 的 12416、18944 两处捐赠 context 错误，12736 正确。R022 默认路径门、T17 donor→实际命中→短/长续算、修复版 T10 分别提供不同证据；CPU 通过不替代这三项 GPU 结果。旧 33/36 冷热分歧中有多少能由 D14 消除，尚无新读数。

数据发布因此保留冷输出/计时测量，命中后输出和多轮质量的受影响子结论保持 `hypothesis`。基线合入与新数据验收按 [第二轮交接](../plan/CODEX_HANDOFF_20261004b.md) 执行。
