# D10 服务级接线差距（代码审查）

本文件记录为何 D10 不能把两个现有 `model.forward()` 或两个 CUDA graph 直接并发，
以及达到真正两请求服务路径必须完成的边界。当前提交仅完成 CUDA copy/compute
可行性原型与 R045 两记录受控入口；不是服务级实现或性能结果。

| 边界 | 当前源码与共享状态 | 必需的服务级改动 |
|---|---|---|
| LRU 专家选择 | `moe/offload_kernels.py:ensure_experts` 将每次请求写进同一 `slot_for_id`、`id_of_slot`、`usage`、`step`、`src_indices`、`evict_slots`、`num_indices` | 每 lane 保有独立的这些设备计划张量；`lru_ensure` 只可看见本 lane 的非重叠 cache 范围及其 slot base。 |
| 专家权重槽 | `moe/offload_cache.py:copy_missing` 根据全局 `_pending_src_layer` 和共享 bank cache 执行复制 | 以 lane context 取代 `_pending_src_layer`；bank cache 按 lane 切片或预留固定 staging rows，并在 completion event 后才释放。 |
| MoE 调用点 | `layers/moe.py:_decode_routed` 在一个层调用内立即 `ensure_experts -> copy_missing -> _expert_gemm` | 需要可分割的 `plan/copy/compute` 接口，让 lane A 的层 compute 与 lane B 的同层 copy 间插入事件边。 |
| 模型执行 | Qwen/GLM 模型的 `forward()` 自己遍历全部 decoder blocks | 给目标 Qwen3.8 路径增加受限的逐层 decode iterator，保留各 lane hidden state、KV 写入和位置；不得用两个完整 forward 重放替代。 |
| 引擎/图 | `engine/engine.py:forward_batch` 以整批 `model.forward()` 作为 graph replay 或 eager 调用 | D10 仅在显式开发开关、恰好两条 decode request、且 graph 禁用时选择新路径；其余批次仍走原路径。双 lane static graph 是后续独立契约，不能复用既有 graph。 |
| 调度与采样 | `scheduler/scheduler.py:_prepare_batch` 已把两个 decode 请求作为一个普通 batch 准备，之后 engine 一次采样并 `complete_one()` | scheduler 必须标记成对的 lane 资源，但不能提前提交；新路径结束后一次性执行原有采样、token D2H event、`complete_one()` 与异常回滚语义。 |

## 最小安全接线顺序

1. 先实现并测试 lane-local LRU plan 与 bank slot slice；测试必须证明 A 的 eviction
   不改变 B 的 `slot_for_id` 或 bank row。
2. 再把目标模型拆为逐层 decode，并在每层运行 `copy(A) -> compute(A) + copy(B) ->
   compute(B)`；对 eager 基线做逐 token 等价比较。
3. 最后才在 engine/scheduler 加默认关闭的选择条件，并以原 R045 两个 128 / false 输入及
   新的 256 / true 输入测量。每一路需严格大于 30 tok/s，且 T16 与逐层 T05 证据齐全。

在第 1 步之前强行复用 `OffloadMoeCache` 会让 B 的 `lru_ensure` 覆盖 A 尚待
`copy_missing` 消费的 copy plan；在第 2 步之前强行复用完整 `model.forward()` 会让两个
调用各自完成整个网络，根本没有每层错相位边界。这两种做法都不能作为 D10 实现。
