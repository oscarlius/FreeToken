# D14 命中续算初始状态的影响

核查对象是 `E2-base@23f2e2caa3395837c9474735ffc83321f3b9b5a1`，
修复候选是 `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42`。

结论：相对坐标问题影响实际计算。它不限于快照元数据，也不限于 n-gram。
源码能证明错误分支会被执行；受影响请求的实际输出与修复后的等价性，仍需
T17 和 T10 实测。不能以源码或 CPU 门代替 GPU 接受。

证据链：

1. 父树 `python/freetoken/engine/engine.py::_build_layer_major_chunks` 把
   子请求 `cached_len` 设置为相对 `lo`。即使外层命中了非零前缀，首块仍为 0。
2. `python/freetoken/attention/linear.py::build_fla_metadata` 从
   `r.cached_len > 0` 推出 `has_initial_state`，并把零长度请求的 live slot
   放入 `fresh_state_indices`。
3. `python/freetoken/models/qwen4_exp/gdn.py` 的预填路径把这个标志传给
   `_conv_prefill`，并对 `fresh_state_indices` 调用 recurrent state
   `index_fill_(..., 0.0)`。已恢复的 GDN 初始状态因此被清零。
4. `python/freetoken/models/qwen4_exp/ple.py::build_ple_metadata` 对 fresh
   请求使用 EOS 填充的 n-gram 初始上下文，PLE conv 也读取 fresh 标志。
5. 后续子块继续使用首块产生的状态，所以影响会沿本次续算传播。

这一坐标缺陷的直接触发范围：非零前缀命中，随后被准入为层优先预填并
拆成子块。在当前默认预算下，需要单请求剩余预填超过 4096 token，且满足
该路径的其他准入条件。短后缀不能单独验证这一问题。另一个捐赠快照指针
缺陷仍可能影响短后缀命中，两个范围需要分别报告。

D14 将子块坐标改为外层原点加相对偏移，并投影外层的单一快照计划。
`tests/engine/test_layer_major_tracks.py` 检查非零首块的绝对坐标、
`has_initial_state=True` 和空的 `fresh_state_indices`。固定源码的 CPU 对照
已有修复前 13 failed、修复后 13 passed；R022 真实模型 T16 已独立复核通过。
T17 R023 已封存为 `not_met`：恢复复制四角色通过，但8192边界短尾续算在
第37个采样token与全冷计算分叉，三个浮点状态角色不同。冷臂和暖臂预填
路径不同，尚未隔离分叉原因。详见[实测反例](T17_R023_COUNTEREXAMPLE_20261004.md)。

T17 必须保留真正准入的 cached token 数、首子块状态标志、四角色恢复张量、
实际采样 token ID 和完整输出。短尾段与超过 4096 token 的尾段均需覆盖。
T10 继续报告冷对冷、热对热、冷对热计数，并保留分叉点，不预先断言所有
确定性的浮点路径差异会消失。
