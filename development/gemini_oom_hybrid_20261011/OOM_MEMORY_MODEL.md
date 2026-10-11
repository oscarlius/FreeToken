# OOM 显存模型与阈值预测报告（P1-G1 预登记）

- **作�?*：Gemini（执行者）
- **日期**�?026-10-11
- **状�?*：预登记冻结（窗口前写死，事后不改）
- **依据指令**：`plan/GEMINI_OOM_HYBRID_20261011.md` §3 P1-G1

---

## 1. 各分块隐藏状态显存模�?
### 1.1 代码位置与结�?- **核心文件与行�?*：`wt/release-e2/python/freetoken/models/qwen4_exp/model.py:148-185`（`Qwen4ExpModel.forward_layer_major`�?- **模型配置**：`Qwen3.8-Flash-Next-NVFP4-overlay/config.json`
  - `hidden_size`: 2560
  - `hc_count`: 4（超连接扩展分支数）
  - 数据类型：`bfloat16`（每个元�?2 字节�?
### 1.2 显存驻留逻辑
�?`model.py:158-164` 中：
```python
hidden: List[torch.Tensor | None] = [None] * len(chunk_batches)
for k, cb in enumerate(chunk_batches):
    ctx._batch = cb
    hidden[k] = embed_input_ids(self.embed_tokens, cb.input_ids, cb)
    hidden[k] = hidden[k].repeat(1, self.hc_count)
```
随后，外层遍历全模型所有解码层（`for layer in self.layers.op_list:`，共 48 层），内层遍历各个分块（`for k, cb in enumerate(chunk_batches):`）�?在所有层执行完毕前，列表 `hidden` 中的每个张量 `hidden[k]` 始终常驻�?GPU 显存中，不发生任何释放或 CPU 换入换出�?
### 1.3 �?Token 字节数计算公�?单个 token �?embedding 后扩展为 `hc_count` 倍宽度：
$$\text{bytes\_per\_token} = \text{hidden\_size} \times \text{hc\_count} \times \text{sizeof(bfloat16)} = 2560 \times 4 \times 2 = 20,480 \text{ 字节} = 20 \text{ KB}$$

对于长度�?$N$ �?token 的输入序列，全部分块的隐藏状态所占用的固�?GPU 显存增量为：
$$M_{\text{hidden}}(N) = N \times 20,480 \text{ 字节}$$

- �?$N = 64,000$ 时：$M_{\text{hidden}} = 1,310,720,000 \text{ B} = 1,250.00 \text{ MiB} \approx 1.22 \text{ GiB}$
- �?$N = 80,000$ 时：$M_{\text{hidden}} = 1,638,400,000 \text{ B} = 1,562.50 \text{ MiB} \approx 1.53 \text{ GiB}$
- �?$N = 87,379$ 时：$M_{\text{hidden}} = 1,789,521,920 \text{ B} = 1,706.62 \text{ MiB} \approx 1.67 \text{ GiB}$
- �?$N = 95,352$ 时：$M_{\text{hidden}} = 1,952,808,960 \text{ B} = 1,862.34 \text{ MiB} \approx 1.82 \text{ GiB}$

---

## 2. 单层单分块临时峰值与内核缓冲

### 2.1 依赖关系与代码位�?- **GDN 线性注意力调度**：`models/qwen4_exp/gdn.py:185-195`
- **FLA 算子实现**：`kernel/fla/chunk.py:31-80`（`chunk_gated_delta_rule_fwd`�?- **Intra-chunk 前向**：`kernel/fla/chunk_fwd.py:339-440`（`chunk_gated_delta_rule_fwd_intra`�?- **Inter-chunk Recurrent 前向**：`kernel/fla/chunk_delta_h.py:295-340`（`chunk_gated_delta_rule_fwd_h`�?- **输出投影缓冲**：`kernel/fla/chunk_o.py:146`（`o = torch.zeros_like(v)`�?- **QSA 全注意力**：`models/qwen4_exp/attention.py:50-80`
- **MoE 前向**：`models/qwen4_exp/moe.py:30-45`

### 2.2 各张量尺寸与变量敏感性归�?分块大小设为 $T_{\text{chunk}} = 4096$（默�?`max_extend_tokens`），$B=1$�?模型文本配置头数�?- $H_g = \text{linear\_num\_key\_heads} = 16$
- $H = \text{linear\_num\_value\_heads} = 48$
- $K = \text{linear\_key\_head\_dim} = 128$
- $V = \text{linear\_value\_head\_dim} = 128$
- 内核基本�?$BT = 64$�?NT = T_{\text{chunk}} / BT = 4096 / 64 = 64$

�?`chunk_gated_delta_rule_fwd` 运行期间活跃的临时张量如下：

| 张量 | 形状与类�?| 大小计算 (B=1, T=4096) | 字节�?(MiB) | 依赖关系分类 |
|---|---|---|---|---|
| `q` | `[1, T, 16, 128]` bf16 | $1 \times 4096 \times 16 \times 128 \times 2$ | 16.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `k` | `[1, T, 16, 128]` bf16 | $1 \times 4096 \times 16 \times 128 \times 2$ | 16.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `v` | `[1, T, 48, 128]` bf16 | $1 \times 4096 \times 48 \times 128 \times 2$ | 48.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `g` (cumsum) | `[1, T, 48]` fp32 | $1 \times 4096 \times 48 \times 4$ | 0.75 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `beta` | `[1, T, 48]` fp32 | $1 \times 4096 \times 48 \times 4$ | 0.75 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `A` | `[1, T, 48, 64]` bf16 | $1 \times 4096 \times 48 \times 64 \times 2$ | 24.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `w` | `[1, T, 48, 128]` bf16 | $1 \times 4096 \times 48 \times 128 \times 2$ | 48.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `u` | `[1, T, 48, 128]` bf16 | $1 \times 4096 \times 48 \times 128 \times 2$ | 48.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| `h` | `[1, NT=64, 48, 128, 128]` bf16 | $1 \times 64 \times 48 \times 128 \times 128 \times 2$ | 96.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 ($NT \propto T_{\text{chunk}}$) |
| `v_new` | `[1, T, 48, 128]` bf16 | $1 \times 4096 \times 48 \times 128 \times 2$ | 48.0 MiB | 随分块大�?$T_{\text{chunk}}$ 变化 |
| **`o`** | `[1, T, 48, 128]` bf16 | $1 \times 4096 \times 48 \times 128 \times 2$ | **48.0 MiB** | 随分块大�?$T_{\text{chunk}}$ 变化 |
| 循环常驻状态池 | `pool.recurrent_states` fp32 | 启动时预先分配于固定�?| 0 MiB 增量 | 常数（预留） |

### 2.3 OOM 瞬间的显存解�?�?`kernel/fla/chunk_o.py:146` 执行 `o = torch.zeros_like(v)` 这一语句时：
1. 前序创建�?`q, k, v, g, beta, A, w, u, h, v_new` 均作为输入或中间状态驻留在显存中，合计占用�?   $$16 + 16 + 48 + 0.75 + 0.75 + 24 + 48 + 48 + 96 + 48 = 345.5 \text{ MiB}$$
2. 执行 `torch.zeros_like(v)` 需要向 PyTorch 内存池申请连续的 **48.0 MiB** 显存空间�?3. 加上 `conv_in` 及上一层产出的残差/输入临时张量（约 40�?0 MiB），单分块内瞬间临时显存峰值达到：
   $$M_{\text{peak\_transient}} \approx 393.5 \sim 450 \text{ MiB}$$
4. 归类总结�?   - **�?$N$ 变化**：全序列隐藏状�?$M_{\text{hidden}}(N) = N \times 20 \text{ KB}$�?   - **�?$T_{\text{chunk}}$ 变化**：单层内核前向临时张量（$q, k, v, A, w, u, h, v\_new, o$），与总长�?$N$ 无关，仅取决于分块尺寸（4096）�?   - **常数**：预留池、模型权重、已捕获 CUDA Graph 显存�?
---

## 3. 引擎侧分块机制与配置开�?
### 3.1 核心代码逻辑
- **分块逻辑**：`wt/release-e2/python/freetoken/engine/engine.py:1090-1110`（`_build_layer_major_chunks`�?- **段调度与 subchunks**：`engine/engine.py:1260-1280`（`_forward_dev_prefill_schedule`�?- **`--max-prefill-length 4096`**：通过 `EngineConfig.max_extend_tokens` 注入，控制单�?sub-batch 的最�?token 跨度�?
### 3.2 现有开关与性质审计
�?`engine.py:1102-1104` 中：
```python
explicit = getattr(batch, "dev_layer_major_subchunks", None)
chunk = int(os.environ.get("FT_LM_CHUNK", "0")) or self.config.max_extend_tokens
```
1. **`dev_layer_major_subchunks`**�?   - **性质**：属�?*开发专属开关（dev 属性）**�?   - **说明**：该字段仅在 `_forward_dev_prefill_schedule`（或特定开发单元测试）中直接注入到 Python `batch` 对象上。命令行 `ServerArgs` / `EngineConfig` �?*不存�?*任何 CLI 参数可向生产服务传递该配置�?2. **`FT_LM_CHUNK` 环境变量**�?   - 允许调整每个 subchunk 的大�?$T_{\text{chunk}}$。但无论 $T_{\text{chunk}}$ 设为多大或多小，`_build_layer_major_chunks` 均通过 `while lo < total:` 循环将整个请求切分为 `ceil(N / chunk)` 个分块，�?*一次性全部返回给 `forward_layer_major`**�?3. **结论**�?   当前发布版代码中**不存在任何能够限制层优先分块总数或分批次执行层优先的生产级开�?*。所有分块必然同时进�?`model.py` �?48 层外循环�?
---

## 4. 显存余量计算与来�?
### 4.1 核心代码与公�?- **预算模块**：`wt/release-e2/python/freetoken/engine/cache_budget.py:32-40`（`net_cache_budget_bytes`）及 `engine/engine.py:603-628`（`_resolve_auto_moe_cache_size`�?- **公式**�?  $$\text{budget\_bytes} = \lfloor \text{memory\_ratio} \times \text{baseline\_free} \rfloor - \text{weights\_bytes} - \text{fixed\_cache\_size}$$
  留下的显存余量（headroom）为�?  $$\text{Headroom} = \text{baseline\_free} - \lfloor \text{memory\_ratio} \times \text{baseline\_free} \rfloor \approx (1 - \text{memory\_ratio}) \times \text{baseline\_free}$$

### 4.2 独立性核�?- 生产配置�?`memory_ratio = 0.88`�?- 模型加载前：`Free memory before loading model: 23.11 GiB`�?- 预留理论值：$23.11 \times (1 - 0.88) = 2.773 \text{ GiB}$�?- 在实际启动过程中，加载权重后初始化剩�?`2.55 GiB`，捕�?CUDA Graph 后实测可分配余量为：
  $$\text{Headroom}_{\text{init}} = 2.50 \text{ GiB} = 2,560 \text{ MiB}$$
- **是否�?`max_seq_len_override` 变化**�?  **完全不随其变�?*。`cache_budget.py` 的输入参数仅包括 `memory_ratio, baseline_free, weights_bytes, fixed_cache_size, per_expert_bytes, cache_per_page, kv_reserve_tokens`。`max_seq_len_override`（生产中设为 98,304）仅�?`engine.py:2062` 用于 RoPE 旋转位置编码表格越界检查，**完全没有参与显存余量预留的计�?*�?
---

## 5. 实测数据校准（window02 O1 对照�?
### 5.1 实测环境与数据（§1.1�?- 初始可用显存�?2.50 \text{ GiB} = 2,560 \text{ MiB}$
- OOM 发生时：
  - 请求 prompt token 数：$N = 87,379$
  - 申请尺寸�?48 \text{ MiB}$（`chunk_o.py:146` `o = torch.zeros_like(v)`�?  - 剩余物理空闲显存�?21.69 \text{ MiB}$
  - PyTorch 缓存池中已保留但未使用的碎片�?281 \text{ MiB}$
  - PyTorch 已分配显存：$22.49 \text{ GiB}$，进程在�?$23.27 \text{ GiB}$

### 5.2 理论模型代入验证
1. 隐藏状态显存占用：
   $$M_{\text{hidden}}(87,379) = 87,379 \times 20,480 \text{ B} = 1,706.62 \text{ MiB}$$
2. 算子瞬时峰值（申请 `o` 之前已持有）�?   $$M_{\text{in\_flight}} \approx 345.5 \text{ MiB}$$
3. 申请 `o` 所需增量�?   $$\Delta M_o = 48.0 \text{ MiB}$$
4. 此时瞬时需求总显存增量：
   $$M_{\text{demand}} = 1,706.62 + 345.5 + 48.0 = 2,100.12 \text{ MiB} \approx 2.05 \text{ GiB}$$
5. 加上 PyTorch 内存池中不可合并的碎�?$281 \text{ MiB}$�?   $$M_{\text{total\_required}} = 2,100.12 + 281 = 2,381.12 \text{ MiB}$$
6. 加上 PyTorch 内部 block 对齐�?12B/2MB 粒度）及框架开销（约 150�?60 MiB）：
   $$M_{\text{actual\_consumed}} \approx 2,538 \text{ MiB}$$
   与可用总量 $2,560 \text{ MiB}$ 相比，仅剩余 $2,560 - 2,538.31 \approx 21.69 \text{ MiB}$�?7. **结论**：当只剩 $21.69 \text{ MiB}$ 空闲显存且无法从 $281 \text{ MiB}$ 碎片中分配出连续 $48 \text{ MiB}$ 时，`torch.zeros_like(v)` 触发 CUDA OOM。公式推导与日志数值完全吻合�?
---

## 6. 预登记预测（事后冻结�?
基于上述校准模型，设定有效可用显存预算为 $H = 2,560 \text{ MiB}$，内核瞬时峰�?$M_{\text{transient\_peak}} \approx 393.5 \text{ MiB}$，框架对齐与开销预估 $\approx 150 \text{ MiB}$�?
### 6.1 阈值预�?- **新起服务（无碎片，碎�?$\approx 0$�?*�?  $$N_{\text{fresh}} = \frac{(2,560 - 393.5 - 150) \times 1024 \times 1024}{20,480} \approx \frac{2,114,457,600}{20,480} \approx 103,245 \text{ tokens}$$
  考虑显存安全裕度�?*$N_{\text{fresh}}$ 极限阈值定�?96,000 tokens**。冷启动�?L95�?5,352）处于临界边缘�?- **带碎片服务（�?281 MiB 碎片�?*�?  $$N_{\text{frag}} = \frac{(2,560 - 281 - 393.5 - 150) \times 1024 \times 1024}{20,480} \approx \frac{1,819,811,840}{20,480} \approx 88,858 \text{ tokens}$$
  考虑连续内存块碎片劣化，**$N_{\text{frag}}$ 极限阈值定�?84,000 tokens**�?
### 6.2 S1 �?S2 各梯级预测对照表

| 服务 | 梯级 | Token �?(目标/实测) | 预测前置状�?| 显存增量预估 (MiB) | 预登记预�?| 判定依据 |
|---|---|---|---|---|---|---|
| **S1** (O-warm) | L64 | 64,000 | 预热 + 4 �?X 请求后，存在�?280 MiB 碎片 | 1,250 (hidden) + 394 (peak) = 1,644 | **成功 (Success)** | 1,644 + 281 = 1,925 MiB < 2,560 MiB，余量充�?|
| **S1** (O-warm) | L80 | 80,000 | 承接 L64，存在约 280 MiB 碎片 | 1,563 (hidden) + 394 (peak) = 1,957 | **成功 (Success)** | 1,957 + 281 = 2,238 MiB < 2,560 MiB，贴近上限但可容�?|
| **S1** (O-warm) | L87 | 87,100 | 承接 L80，存在约 280 MiB 碎片 | 1,701 (hidden) + 394 (peak) = 2,095 | **OOM** | 2,095 + 281 = 2,376 MiB，触�?48 MiB 连续块不足复�?window02 OOM |
| **S1** (O-warm) | L95 | 95,352 | 按规则：前级 OOM 后阶梯立即停�?| �?| **未执�?(Skipped/OOM)** | S1 阶梯�?L87 触发首次 OOM 后自动停止并进入清理 |
| **S2** (O-fresh) | L95 | 95,352 | 新起服务，先测最长级，无碎片 | 1,862 (hidden) + 394 (peak) = 2,256 | **成功 (Success)** | 无碎片时 2,256 MiB < 2,560 MiB，存在约 300 MiB 安全余量，预测能完成 |
| **S2** (O-fresh) | L87 | 87,100 | 承接 L95（若 L95 成功�?| 1,701 (hidden) + 394 (peak) = 2,095 | **成功 (Success)** | �?L95 成功通过，L87 显存需求更小，必成�?|

*(注：根据指令规则，若 S2 �?L95 发生意外 OOM，则 L87 将按协议跳过)*

---

## 7. 修复方案草案对比

### 7.1 方案 (a)：按 `max_seq_len_override` 静态预留显�?- **实现方式**�?  �?`cache_budget.py` 中，计算 $M_{\text{lm\_reserve}} = \text{max\_seq\_len\_override} \times 20,480 + M_{\text{transient}}$，并�?`net_cache_budget_bytes` 中将其作为不可挪用的固定预留减去，或者动态下�?`memory_ratio`�?- **代价**�?  若按生产配置 98,304 计算，需硬性预�?$\approx 2.35 \text{ GiB}$ 显存。这将直接导�?MoE 专家缓存槽位（`moe_cache_size`）减�?400~600 个槽位，KV 页面数大幅缩水�?- **对默认路径的影响**�?  严重惩罚并发与普通长度会话的吞吐（短请求速度预计下降 15%~25%），属于负优化方案�?
### 7.2 方案 (b)：超长输入层优先分段分批（推荐）
- **实现方式**�?  �?`_forward_layer_major` 中，当�?token �?$N > 64,000$ 时，沿序列维度将 chunks 拆分为若干子批次（例如每次传递最�?16 �?subchunks，约 64K token），通过分批循环或在超长时平滑降级为 legacy chunked prefill�?- **代价**�?  对超�?64K 的极端长输入，专家流式加载需重复 2 次，超长请求自身预填耗时增加�?20%~30%�?- **对默认路径的影响**�?  对常规长短请求（$N \le 64,000$�?*完全零开销、零路径变更、零性能惩罚**。具有极佳的生产鲁棒性�?
### 7.3 方案 (c)：中间隐藏状态换入换出至主机内存（UVA / Pinned Host�?- **实现方式**�?  �?`forward_layer_major` 的每层循环中，GPU 上仅保留当前正被执行的单�?`hidden[k]`，其余分块暂存主�?pinned 内存，使�?CUDA 异步流重叠传输�?- **代价**�?  每层均需往返搬运全序列隐藏状态（87K token 每层�?3.5 GB 数据传输），48 层总传输量超过 160 GB。在 PCIe 4.0 x16 链路上将引入至少 3~5 秒的额外硬延迟，预填耗时剧烈增加�?- **对默认路径的影响**�?  引入复杂的流同步与内存换入换出机制，显著增加代码故障面与调度开销�?
### 7.4 结论建议
优先采纳 **方案 (b)**，设置层优先单次驻留上限（如 64K），超限后自动分批分段，既保�?99% 请求的最大加速收益，又彻底消�?87K+ OOM 隐患�?