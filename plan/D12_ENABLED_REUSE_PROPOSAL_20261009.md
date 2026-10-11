# D12 enabled 路径复用验证提案（实施前）

**状态：提案，不是准入或运行授权。** 候选固定为 `8f6a912ea6066f192c37dc74435efc9da0c7591c`。现有 D12 enabled namespace/PID 映射/control pipe/watchdog/host-FD 线保持 **FROZEN**：本提案不改其代码、不补测试、不启动服务或 GPU。`E2-R063-gate-D12` 的默认关闭路径为 4 服务/48 calls，已获 01:00 夜间串行授权、待 b/c 后执行；它只能成为后续默认基线，不能证明 enabled。

## 目标与可复用边界

在 dell 的既有 service owner 生命周期内，未来验证分成相互独立的层次：

| 层次 | 复用物 | 能回答的问题 | 不能据此声称的内容 |
| --- | --- | --- | --- |
| 默认基线 | [T16 四臂默认路径门](01_测试与调研/T16_开发交付默认路径逐位门.md) | parent/new、D0 on/off 的冷输出、prefill 序列和 D0 H2D/D2D bytes 比较，并记录 checkpoint-tax | enabled 分支、checkpoint-tax 数值等价、缓存命中或物理 batch 已正确 |
| 服务证据读取 | [D16 path readers](../development/e2d16-readers/scripts/equiv_suite/path_readers.py) | 对已形成的 batch/parking/cache/interleave 证据对象作非准入读取 | 产生 native capture，或把普通 HTTP/service-owner receipt 自动当作 reader 输入 |
| 状态/数值 | [D03 state-envelope v2](../development/d03_state_envelope_v2/READINESS.md) 与既有 logits/state reader | 已绑定 UID/prefix/layer/shape/dtype 的 state envelope 与 logits 比较 | 未绑定请求的文本相等即代表 state 或数值等价 |
| 性能观测 | [AIPerf toolchain](../evaluation/toolchain/README.md) | 真实服务 API 的原始请求/响应和 TTFT、TTFO 报告 | branch 命中、state 正确性、物理 batch 或目标模型性能已证实 |

服务由 `dell` 身份的 service owner 启停、观察和清理；D16/D03/AIPerf 只是既有读取或客户端，不取得 host-FD 全宿主独占，也不替代已有 owned-lifecycle 准入。

## 不超过一人日的准备范围

1. 固定候选、默认配置和既有输入身份；在已授权的串行时段执行并封存 R063 默认关闭 4 服务/48 calls，作为 enabled 比较的外部基线。
2. 做一份只读接口映射表：每个将来服务实例的 owner identity、D16 run/slot/event 证据字段、D03 UID/prefix/layer/logits 输入身份，以及 AIPerf endpoint/raw-artifact 位置必须一一对应并可封存复查。
3. 以既有 T06 分段资料约束输入选择，随后在实际候选运行中记录 D0 `subchunks` 与 MoE child context；只在此映射完成后评估 future thresholds `64/256/512/1024`。
4. 由独立复核确认封存源、输入、默认基线与上述映射后，才另行提出执行矩阵和 GPU 运行申请。

本提案不预先给出 enabled 服务数、调用数或阈值臂数：这些数只有从已执行的默认 gate 和身份映射中推得后才能提出并审批。

## 已知证据与必须关闭的接口缺口

- [T06 分段纠正说明](../development/D12_ENABLED_INPUTS_AND_SEGMENT_CORRECTION_20261008.md) 说明阈值比较的是单个 MoE forward prefill segment，不是整条业务 suffix；历史记录为 51 个 warm segment，其中 35 个不超过 256、15 个恰为 64。它还明确指出 routing trace 会改变切分、候选可能按 4096 内部分块，因此这些历史数不能作为 enabled 命中分子或性能收益的预测。`64/256/512/1024` 在此仅是将来待实测的阈值集合。
- D16 实际可复用的是 `equiv_suite/path_readers.py` 的 CPU-only **读取**接口，而不是 `d16_native_process_collection_v6.py` 的 collector/execution layer。batch/interleave 输入必须已有 `batch`、`repeat`、`singles` 三个独立 run：每个都含 `{pid,start_ticks,execution_id}`、run `event_identity`、slot map、每 slot 的独立 event、64-hex `input_ids_sha256`、`token_ids`、`text`、`actual_cached_tokens` 与 `segment_reasons`；batch 还须有实际 slot 的 `batch_shape`。如有 fork，还须有已保留原始 receipt bytes 的 D03 top-2 binding。parking/cache/interleave 分别要求四个 restore roles、冷/暖独立 process/event/cache hit-miss，或两 slot 的稳定 prefill/decode event 顺序。所有输出保持 `admitted: false`。当前冻结的 D12 service-owner/namespace 产物没有已证明到这些对象字段的映射；不能以通用 JSON、HTTP timing 或 PID receipt 代替，也不能为此启动或改造 collector。
- D03 state-envelope 现有语义包含 identity、UID、prefix、layer provenance、shape、dtype、nonfinite 与数值 envelope。现有 T06 的请求/分段资料尚未把 enabled worker 的实际 input IDs、UID、state dump、logits 输出绑定到这些 reader 输入；没有该映射，不能使用 D03 结果作 enabled 正确性结论。
- AIPerf 只应在功能和状态证据已满足后对真实服务记录原始报告；须同时保留并报告 TTFT 和 TTFO。其现有 loopback smoke 明确是协议证据，不是模型性能证据。
- R063 默认关闭 4/48 尚未执行，故目前没有可比较的候选默认终态。任何 default/enabled 对照、阈值收益、服务规模或 call 总数均待该事实和接口映射补齐。

## 后续准入条件

只有在默认 R063 终态、D16/D03 身份映射、实际 subchunk/child-context 证据及独立封存复核全部存在后，才可为 `64/256/512/1024` 提交具体执行计划。届时仍须把 T16 的默认等价结论、D03 状态/数值结论、D16 path-reader 结论和 AIPerf API 观测分别报告；任何一层缺失都不能用另一层补足。
