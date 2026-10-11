# D19：批不变性只读调查（E3，2026-10-09）

**R065后续实测更新：**服务A两次串行原长请求全文不同，第二次实际cached_tokens=8256；finish/token usage相同，条款a不满足，B/C与R063均未启动。这表明本次差异也出现在同进程冷/热路径，不能继续把“仅由并发批组成导致”当作已证实解释；缓存续算、分块形状及数值路径仍待用户裁定后另行调查。下述调研在R065运行前完成，原not_met保持，任何后续GPU未获新授权。

## 结论边界

**R040j 的 `not_met` 原判定不改判。**已知现象仅为：长度 8257（8192+65）的同一请求，两次并发和一次串行的全文输出彼此不同；短请求 512 的输出对 Y 不敏感。这是值得进入 E3 的复现/判别信号，但不是对根因的证明。尤其是 API 调用时间重叠只能证明客户端并发，不能证明三次请求曾进入同一个物理 GPU batch，也不能证明它们在同一 kernel、相同 batch 形状或相同 CUDA graph 中运行。

本文仅阅读候选工作树 `/data2/FreeToken/wt/e2oom-protocol-restart` 的提交 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`（SSH，已激活 FT venv；未启动 GPU、模型或业务请求）。R065 将验证 481 发布候选的 3/7，结果尚未产生；本文不预判其通过与否。

## 已观察到的实现事实

1. **候选调度器并不把 prefill 与 decode 塞进同一个 `Batch`。**`Batch` 的 phase 是二选一；`_schedule_next_batch()` 先尝试 `prefill_manager.schedule_next_batch(...)`，失败才调 `decode_manager.schedule_next_batch()`（`python/freetoken/scheduler/scheduler.py:1041-1051`）。decode batch 由全部运行中请求按 uid 排序组成，phase 固定为 `decode`（`scheduler/decode.py:32-35`）。因此“chunked-prefill 与 short-decode **物理混批**”不是本提交已证实的实现事实；它须经运行时批次记录证实或证伪。

2. **长 prefill 确会分块，且会与其他 prefill 请求交错。**当本段小于剩余 prompt 时，调度器建立 `ChunkedReq`（`scheduler/prefill.py:259-304`）；随后把 continuation 放回 `pending_list` 前端并在下一轮重排（`384-458`）。同时，调度器默认 overlap 模式会把当前 forward 与前一批结果的 CPU 处理重叠（`scheduler.py:287-307`）。这些事实足以令长请求在不同运行中经历不同的 *prefill batch 组成/形状*，但尚不足以说明该变化导致 token 改变。

3. **R040j/R065 的量化参数指向 NVFP4 Triton；以下才是目标路径证据。**`TritonNvfp4MoEKernel.name` 为 `triton`，其 `apply()` 以 phase 分流：prefill 调 `fused_experts_nvfp4`，decode 调生产用的 `fused_experts_decode_nvfp4_marlin`（`layers/quantization/moe/nvfp4.py:37-78`；NVFP4 方法候选亦以 Triton 居首，`567-572`）。此处的 “marlin” 是 FreeToken 的 Triton inline-dequant wide-load decode 实现，不表示 R040j 改用了 vLLM Marlin backend。

4. **目标 NVFP4 的 prefill grouped GEMM 明确随 M/路由形状改变。**它由 `M=hidden_states.shape[0]` 选择配置：`M<=64` 用 `BLOCK_SIZE_M=16,GROUP_SIZE_M=1`，否则为 `32,8`；`moe_align_block_size(topk_ids, BLOCK_SIZE_M, ...)` 将路由按 expert 对齐、补齐，再以 `EM/BLOCK_SIZE_M × N/BLOCK_SIZE_N` 形成 kernel grid（`moe/fused_nvfp4.py:256-304,323-352`）。kernel 从 `sorted_token_ids` 恢复 token、从 `expert_ids` 取 cache slot（`kernel/triton/nvfp4_fused_moe.py:272-299`），并在 K-loop 中对每个 M×N tile 用 `tl.dot` 累加（`299-339`）。这是“同一请求因同相 prefill batch 组成变化而可能走不同 M-block/grouping”的**实际实现事实**；是否导致 R040j 的 logits 或 token 改变仍待证明。

5. **目标 NVFP4 decode 的已见实现不是跨 program 的 split-K。**它令 `total_routes=M*top_k`，grid 为 `(total_routes, ceil(N/block_n))`；`block_n/block_kw` 由 K 是否超过 2048 决定，不由 M 决定（`moe/fused_nvfp4.py:96-138`）。生产 kernel 对每个 route/N tile 在同一 program 内累加 K partial，最后 `tl.sum(partial, axis=0)`（`kernel/triton/nvfp4_fused_moe.py:172-239`），随后由 `moe_sum_reduce_triton` 汇总 top-k expert 输出（`fused_nvfp4.py:161-202`）。故“NVFP4 split-K 规约顺序改变”目前**不是** R040j 的源码证据；可保留的待测点是 decode M 改变了 route grid/缓冲区形状，或 prefill M 跨 64 触发 grouped-GEMM 配置切换。

MXFP4 的 split-K 代码仅证明候选仓中另一路量化实现存在该技术，和本次 `--quant-backend moe.nvfp4=triton` 目标无直接归因关系，不能作为 R040j 根因证据。

## 发布限制的外部一手依据

vLLM stable 文档（页面日期 2026-09-27，2026-10-09 读取）将 batch invariance 定义为“输出独立于 batch 大小和请求顺序”的**单独 beta 能力**，要求显式设置 `VLLM_BATCH_INVARIANT=1`；启用后使用确定性 kernel、保证跨 batch 数值行为，并关闭可能引入非确定性的优化。见：[vLLM Batch Invariance](https://docs.vllm.ai/en/stable/features/batch_invariance/)。该页的服务例子即使 `temperature=0.7` 也同时给出 `seed=42` 和该开关，说明“贪婪采样”和“批不变性”是不同条件。

SGLang 上游文档在 2026-10-09 读取的 `main@2b94cb4eb5fbab75ace8eec410ea9bd45244912f` 明说：即使 `temperature=0`，标准推理仍可因 dynamic batching 与 GPU reduction order 得到不同输出；其 `--enable-deterministic-inference` 是“batch-invariant operations”的开关，默认 **disabled**，并只列出 FlashInfer、FA3、Triton 三类 attention backend 的支持范围。见固定源码：[deterministic_inference.mdx@2b94cb4](https://github.com/sgl-project/sglang/blob/2b94cb4eb5fbab75ace8eec410ea9bd45244912f/docs/docs/advanced_features/deterministic_inference.mdx)。这是官方上游源码文档而非二手材料；该 SHA 位于滚动的 main，非已声明的 SGLang release 版本，也不能外推为 FreeToken 的默认或支持矩阵。

因此本发布限制应准确写为：**在本次 FreeToken 构建、目标模型、GPU/驱动、量化路径、调度配置均未逐项验证 batch-invariance 的前提下，默认 `temperature=0` 只说明本实现请求意图为 greedy（本地 `SamplingParams.is_greedy`，`core.py:18-30`），不能单独构成“跨并发/批组成输出必相同”的发布保证。**这不是把 vLLM 的硬件或实现要求外推到 FreeToken；它只是官方上游已把 batch invariance 作为额外契约的直接依据。vLLM 该功能仍为 beta，且其已验证模型/平台不等同于本候选。

## E3 待测假设与最小判别设计（不在本卡执行）

| 假设 | 最小判别 | 预期区分信号 |
|---|---|---|
| H1：长 prompt 的 chunk 边界/同相 prefill 组成触发差异 | 固定请求、固定 temperature=0、固定服务配置；只改变另一**prefill** 干扰请求的长度/到达时刻；记录每段 `uid, phase, extend_len, batch size, chunk 边界` 和逐 token id/logit | 仅长请求且差异首现位置与 segment 边界或 batch 形状切换稳定相关 |
| H2：NVFP4 的 batch 形状路径触发差异 | 分两步：只改变同相 prefill 的 M，使其不跨/跨 `M=64`；再让目标进入 decode 后仅改变 decode M。记录实际 batch、phase、NVFP4 kernel/config、top-k 路由和逐 token id/logit | 前者验证 grouped-GEMM config/route padding；后者只验证 route-grid/缓冲区形状。不得把结果标成“split-K”除非 trace 显示实际路径 |
| H3：所谓 prefill/decode 混批 | 记录 scheduler 生成的 `Batch.phase` 与 req uid，核对每次 forward | 若源码语义保持，应只见纯 prefill 或纯 decode batch；若出现混相 batch，先作为实现/观测异常处理 |

所有比较应先检查输入 token ids、采样参数、模型/权重哈希、运行提交、GPU/驱动、环境变量和首个不同 token 的 logits；每个控制条件至少重复到足以区分偶发与稳定现象。R065 3/7 的结论独立归档后再用于发布判断；D19 不替代该验收，也不建议据此修改实现。
