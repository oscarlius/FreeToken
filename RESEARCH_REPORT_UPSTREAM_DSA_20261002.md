# FreeToken 上游调研报告：专家 q⋆ / DSA / PLE·路由表 的实现位置与带宽影响

> **仓库**：`freetoken/upstream-flashml`（https://github.com/FlashML-org/FreeToken）
> **提交**：`d3512b43affe981465e03ee28cbd88f49c39b9aa`（2026-10-01，`fix(ple): fence disk staging against in-flight lookups #588`）
> **论文**：https://arxiv.org/html/2608.16157v1
> **性质**：只读调研。未改任何代码、未在 172.16.108.9 上启动/重启 8095、未下载模型。
> **任务来源**：[RESEARCH_TASK_UPSTREAM_DSA.md](RESEARCH_TASK_UPSTREAM_DSA.md)
> **日期**：2026-10-02
> **本机背景**（只作对照，未上机测）：1×RTX 4090 24GB、双路 Xeon Silver 4310、251GiB、GPU 在 NUMA 1、服务核 `1,3-23`。目标模型：Qwen3.8-Flash-Next、GLM-5.3-Flash。

---

## 一、已实现（文件：行号）

> 路径均相对 `upstream-flashml/`；测试代码在 `tests/`，其余在 `python/freetoken/`。

### 1. 专家卸载与 q⋆

**结论：代码里的 fetch fraction 就是论文的 q⋆。**

| 内容 | 位置 |
|---|---|
| `ensure_experts_hybrid`：每步 miss 只搬前 `max_fetch` 个，超出的 expert_ids 原位改写为 `-1`（留 CPU 算）；`fetch_fraction` 用 Q16 定点数保证 GPU kernel 与 CPU 参考一致 | `moe/offload_kernels.py:43-60`（定点化 :57） |
| fraction 语义注释：**"fetched : cpu = pcie : cpu − pcie"**，即 q/(m−q) = B_P/(B_H−B_P)，代数上等价于论文 **q⋆ ≈ m·B_P/B_H**（含残余带宽修正 B_R = max(B_H−B_P, 0)） | `moe/offload_cache.py:138-143` |
| 引擎默认 `-1` = 自动取 `ft bench bw` 本机实测值；无 profile 时回退固定 cap=1 | `engine/config.py:64-68` |
| 实测入口：`load_hybrid_fetch_fraction`（benched PCIe/CPU 带宽比） | `moe/bench_profile.py:156-165`；`moe/benchbw.py:14,664` |
| 每层每步调用点 | `moe/offload_cache.py:859-873` |
| fetch 子集默认按 **LRU 近因**挑选（优先搬最近活跃专家；`FREETOKEN_HYBRID_FETCH=lowest_id` 可切回路由盲选）——**论文未描述此启发式** | `moe/offload_kernels.py:10-16` |

### 2. 预填：整层双缓冲为主，按需是回退路径

| 内容 | 位置 |
|---|---|
| 引擎默认开启 `moe_prefill_overlap: bool = True` | `engine/config.py:47` |
| CLI 关闭开关 `--disable-moe-prefill-overlap` | `server/args.py:739-742` |
| 每 bank `[2, num_experts, ...]` 双缓冲视图 + 独立 copy stream + 事件对 | `moe/offload_cache.py:269-278` |
| 命中行 D2D 聚合 kernel（`prefill_hit_compact`） | `moe/offload_kernels.py:63-82` |
| `prefill_hit_d2d`：已驻留专家不再过 PCIe，仅 miss 走一次 `cudaMemcpyBatchAsync`；条件不满足时**静默**退回整层拷贝 | `moe/offload_cache.py:111-116` |

**退回按需搬运的三个条件：**

1. `cache_size < 2 × num_experts` → 启动断言失败（`offload_cache.py:163-166`），需加缓存或关 overlap——**不是静默回退**；
2. `prefill_hit_d2d` 前提不满足 → **静默**退回整层拷贝（`offload_cache.py:111-116`）；
3. LOCKED/PAGEABLE 驻留层 → `copy_missing` 按需 pageable 分支（`offload_cache.py:212`）。

**张量并行 / 专家跨卡切分：无。** `moe/` 全目录无 TP 分支；目标模型加载器硬拒 TP>1：

- `models/qwen4_exp/weight.py:207`（Qwen3.8-Flash-Next）
- `models/glm5_next/weight.py:183,258`（GLM-5.3-Flash）

（TP 通信基建存在于 `distributed/impl.py:25-44`、`kernel/pynccl.py`，但专家路径完全不接。）

### 3. DSA（GLM 侧）

| 内容 | 位置 |
|---|---|
| GLM-5.3-Flash（glm5_next）确认使用：MLA 权重吸收 + **kpool DSA indexer**；每个 DSA 层自带 indexer（无 IndexShare），索引 K 缓存每 4 token（kpool=4）一条，select_k = index_topk/kpool；投影归本模块所有 | `models/glm5_next/attention.py:1-19` |
| 后端：全 Triton gathered-KV sparse MLA；DSA 解码路径整体进 CUDA graph（无状态 kernel，`prepare_for_replay` 摆地址）；dense = 同 kernel 的 identity-selection 退化情形；长 prefill 按查询块 causal top-k | `attention/dsa.py:1-37` |
| indexer 打分 + causal top-k（选择语义与 dsv4_indexer ratio=1 共享） | `attention/dsa_indexer.py` |
| kpool 变体索引器 | `attention/dsa_indexer_kpool.py` |
| KV 放置：**显存**。`MLAKVCache` latent slab + `DSAKVCache` 索引 key slab + `KpoolDSAKVCache` 1/ratio 影子，原子 rebuild | `kvcache/dsa_pool.py:1-10` |
| 权重放置：**GPU**（indexer 投影是常规模型参数，随稠密权重加载） | `models/glm5_next/attention.py:17-19` |
| 解码**不进专家槽**：KV 池与 MoE slot cache 是两套独立分配 | `kvcache/dsa_pool.py` vs `moe/offload_cache.py` |
| 元数据 pinned int32、prefill 打分 transient 上限 128MB（fp32 logits 分块） | `attention/dsa.py:41-44` |

### 4. Qwen QSA（与 GLM DSA 是两套，无共享缓存）

| 内容 | 位置 |
|---|---|
| QSA 全注意力层，12/48 层（Qwen3.8-Flash-Next） | `models/qwen4_exp/attention.py:1` |
| QSA 池：分页 GQA K/V + **1/ratio 压缩索引行影子 slab** + `pending_ring`（跨 forward 的 pre-RoPE 索引键） | `kvcache/qsa_pool.py:1-8` |

两套互不共享缓存：`dsa_pool` 属 GLM 架构、`qsa_pool` 属 qwen4_exp 架构，同一进程只服务一个模型，不会共存。

### 5. 路由表（三类，分开陈述）

**① MoE gate —— 确认常驻 GPU**

- `models/qwen4_exp/moe.py:22,24`：`self.gate` / `shared_expert_gate` 是常规 GPU 参数；
- host bank 只收 routed experts（`models/qwen4_exp/weight.py:205` 附近 docstring："the routed experts … always come from the offload cache's expert reader"）。

**② Qwen PLE / n-gram 表 —— 钉在主机内存，UVA 直取，不进显存、无热行缓存、非磁盘逐 token**

| 内容 | 位置 |
|---|---|
| PLE 定义：40M 行 × 160 FP8 = **47.7 GiB** 整表；生产后端 `PinnedUVATable`，oracle 对照 `GpuResidentTable` | `models/qwen4_exp/ple.py:1-16` |
| `GpuResidentTable`：整表进显存——**仅作 oracle**，非生产路径 | `ple.py:72-96` |
| `PinnedUVATable`：整表**钉住主机内存**，Triton kernel 经 UVA 直取行；staging buffer 按 graph 尺寸各一 + 一个可增长 buffer；prefetch 走私有流提前发射、`lookup` 时 join | `ple.py:120-131,133-204` |
| gather kernel `ple_gather_rows` | `kernel/triton/ple.py` |
| disk 后端（`--ple-backend disk`）：C++ store 哈希 n-gram 窗口、批量读 checkpoint fp8 shard → pinned staging；captured lookup = 定形 H2D + 反量化 | `models/qwen4_exp/ple_disk.py:1-4` |
| **fence（d3512b4 修复本体）**：graph 路径 pinned buffer 预分配（capture 内 pinned 分配非法）、`_graph_consumed` 事件，`fill()` 重写前 `synchronize()`；eager 路径双 pinned buffer + `_eager_read[slot]` 事件 | `ple_disk.py:146-176,180-193` |
| wait-sync / launch-gating 双模式，`FREETOKEN_PLE_SYNC=auto|wait|gate` 探测选择 | `ple_disk.py:31,166-176`；`kernel/row_store.py:23-31` |

- **与专家预填抢不抢 PCIe**：抢。PLE 行取（UVA gather 或 H2D）与专家整层双缓冲 H2D 共用同一 PCIe/主机内存子系统，**代码中无仲裁/QoS**（观察性结论）。

**③ Engram / GLM 侧同类大表 —— 不存在**

- 全库 grep 零命中；`ple` 只存在于 `models/qwen4_exp/` 下，glm5_next 无同类表。

### 6. 循环状态（KDA/GDN）

| 内容 | 位置 |
|---|---|
| 快照在 prefill 的 **64-token 对齐 chunk 边界**写入可捐赠池槽；恢复用 `has_initial_state=True` 续跑 | `tests/models/test_glm5_next_kda_snapshot.py:3-7` |
| 独立 SSM 状态池（与 DSA 的 KV 池**不是同一个池**） | `kvcache/linear_state_pool.py` |

---

## 二、代码里没有

| # | 项 | 依据 |
|---|---|---|
| 1 | **Engram**（或 GLM 侧 PLE 同类大表） | 全库 grep 零命中 |
| 2 | **专家级张量并行 / 单专家跨卡切分** | `moe/` 无 TP 分支；`qwen4_exp/weight.py:207`、`glm5_next/weight.py:183,258` 在 TP>1 时直接 `NotImplementedError` |
| 3 | **论文的特殊 token 边界锚定检查点**（thinking 段、工具调用、对话轮次） | 论文 §3.1 明确要求；代码快照只按 64-token chunk 边界（`test_glm5_next_kda_snapshot.py:3-7`），未见语义边界锚定逻辑 |
| 4 | **PLE 热行缓存** | pinned = UVA 直取、disk = 每次批读 H2D，无行缓存/淘汰机制 |
| 5 | **PLE 与专家搬运的 PCIe 仲裁** | 两条路共用 PCIe/内存子系统，代码无 QoS |

---

## 三、还不能确定

1. `benchbw.py` 实测 `cpu_bw` 的口径是否已扣除 DMA 并发对主机内存子系统的挤占（论文 B_R 修正）。公式等价已确认（`offload_cache.py:138-143`），测量细节未逐行核完 `benchbw.py` 全文。
2. 论文"q⋆ 取整时至少保留一填"是否为显式不变量——引擎侧只是 fallback cap=1（`engine/config.py:68`），未见显式 clamp。
3. glm5_next 各层 DSA/dense 的层数分布（`attention.py` 头注未写明，仅确认每个 DSA 层自带 kpool indexer）。

---

## 四、对本机的含义

> 三件事里：**哪件改预填搬运量、哪件改解码带宽**。

### 预填搬运量 ← PLE（路由表）

- 每个预填 token 的 PLE 表行都必须过 PCIe：pinned 后端 UVA 直取，disk 后端再加"盘 → pinned → H2D"一跳；
- 与专家整层双缓冲的 H2D **共用同一 PCIe 和内存子系统，且无仲裁**——本机预填期间的搬运竞争就是三方：盘读（disk 后端时）、PLE 行取、专家 H2D；
- 专家搬运量本身的旋钮是 `prefill_overlap` / `prefill_hit_d2d`（`engine/config.py:47,51`），**与 q⋆ 无关**（q⋆ 只管解码）。

### 解码带宽 ← 专家 q⋆（hybrid fetch fraction）

- 每步 miss 的专家按 `pcie : cpu` 带宽比拆分，直接决定每步多少字节走 PCIe、多少留在 CPU 上算；
- 必须本机实测（`ft bench bw`，`bench_profile.py:156`），不是纸面推导——本机 GPU 在 NUMA 1、服务核 `1,3-23`，实测值与 CPU 侧绑定方式强相关。

### DSA/QSA —— 两样都不直接动

- 它们的 KV/索引 slab 全在**显存**（`dsa_pool` / `qsa_pool`），不占 PCIe/主机带宽；
- 唯一间接效应：挤占 24G 显存预算 → moe_cache 变小 → miss 率升高 → 解码专家搬运量**间接**增加。

### 附带稳定性提示

- `d3512b4` 的 PLE fence 修复（`ple_disk.py:146-193`）是 overlap 调度下解码正确性的关键路径——本机若开 `--ple-backend disk` 且用 overlap 调度，应确认运行在这个提交或之后。

---

*按任务要求：本报告未产生任何代码变更，未触碰服务配置。是否改代码待反馈后决定。*
