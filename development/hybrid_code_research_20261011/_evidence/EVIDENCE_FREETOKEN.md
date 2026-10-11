# EVIDENCE_FREETOKEN — FreeToken 侧 cache-miss 专家 CPU 计算路径（只读代码调研）

- 代码版本：服务器 `/data2/FreeToken/wt/release-e2`，提交 `481d3a7`（发布版）。本地只读快照对应 `python/freetoken/` 包。
- 引用约定：所有 `文件:行号` 的路径前缀为 `python/freetoken/...`。
- 标注约定：「读码确认」= 在快照代码中亲眼看到；「推断」= 由代码事实推导；「未找到」= 列于文末清单。
- 与本次调研相关的背景：Qwen3.8 系 MoE，NVFP4 量化专家，decode 时 miss 的专家一部分经 PCIe 取到 GPU（受上限/比例约束），其余在 CPU 上算。服务器为 Xeon Silver 4310 双路（Ice Lake）。

---

## Q1 每层每步：专家在 GPU 算还是 CPU 算，由谁决定

**决策全部在 GPU 侧、device-side 完成（一个单 program 的 Triton kernel），Python 只做结论消费。**（读码确认）

链路（decode、非 prefill）：

1. 路由打分：`OffloadMoELayer.decode_forward` 调 `fused_topk` 得 `topk_weights/topk_ids`（`layers/moe.py:241-246`；外部路由模型走 `routed_forward`，`layers/moe.py:210-234`）。
2. hybrid 分发：`_decode_routed` 中 `cache.decode_target == "hybrid"` → `_decode_hybrid`（`layers/moe.py:305-306`）。注：若某层在 `cpu_layer_ids` 里（`--moe-cpu-layers`），则整层纯 CPU，先被 `is_cpu_layer` 截走（`layers/moe.py:294-304`）。
3. 命中判定 + 取数决策：`_decode_hybrid` 调 `cache.ensure_experts_hybrid(layer_id, topk_ids)`（`layers/moe.py:347`）→ `offload_cache.py:1213-1232` → `moe/offload_kernels.py:43-60` → `_ensure_experts_hybrid_gpu`（`offload_kernels.py:97-125`）→ Triton `_ensure_experts_hybrid_kernel`（`offload_kernels.py:291-410`）：
   - 命中判定：`slot_for_id[layer][e] >= 0`（`offload_kernels.py:341-343`，`slot_for_id` 是 GPU 上的 [L,E] 槽位表，`offload_cache.py:190-195`）。
   - 取数上限/比例：`max_fetch` 固定上限，或 `fetch_frac_q16`（Q16 定点）按比例在 kernel 内由 `num_missing` 现算（`offload_kernels.py:345-355`）。取哪些 miss：默认 `BY_RECENCY`（按 `expert_recency` 最近活跃优先，ties 取小 id；`offload_kernels.py:14-16`、`364-368`、`406-410`），`FREETOKEN_HYBRID_FETCH=lowest_id` 退化为按 id。
   - 结果：`topk_ids` 被原地改写为 cache slot（命中/被取数）或 **-1**（溢出 miss → CPU 算，`offload_kernels.py:400-404`）；`num_indices`=实际取数个数（供 `copy_missing`），`num_missing_full`=封顶前 miss 数（统计）（`offload_cache.py:213-216`）。
   - 全 device-side、定形状，CUDA-graph 安全（`offload_cache.py:1221-1222`）。
4. 消费侧（Python）：`on_gpu = topk_ids >= 0`；`cpu_ids = where(on_gpu, -1, raw)`（`layers/moe.py:350-352`）；CPU kernel 跳过 `id<0`（`cpu_moe_ext.cpp:1596`：`if (e < 0 || e >= num_experts) return;`）。

参数设置点：
- `decode_target`：由 `--moe-strategy` 推导（`engine/engine.py:1562-1568` `_decode_target`，写入 `model_config.decode_target` 于 `engine/engine.py:2040-2042`）；策略族定义在 `moe/__init__.py:3-10`。
- `hybrid_max_fetch` / `hybrid_fetch_fraction` 字段：`moe/offload_cache.py:151-161`（默认 `max_fetch=1`、`fraction=0.0`）。CLI 默认 `--moe-hybrid-max-fetch -1`（auto）（`engine/config.py:62-67`，`server/args.py:759-761`）。
- auto 解析：`engine/engine.py:758-787` `_resolve_hybrid_fetch`：读 `ft bench bw`  profile（`moe/bench_profile.py:156-191` `load_hybrid_fetch_fraction`，优先 overlap 实测对 `pcie_ov/(pcie_ov+cpu_ov)`，否则 `pcie/cpu`），命中则 `hybrid_max_fetch=num_experts`（失效）+ `hybrid_fetch_fraction=fraction`（`engine/engine.py:782-783`）；无 profile 则固定 cap=1（`engine/engine.py:775-781`）。
- 每步实际取几个：在 GPU kernel 内决定（`offload_kernels.py:355` `num_fetch = min(num_missing, max_fetch)`）。

---

## Q2 CPU 读到的专家格式 / 每专家字节数 / NVFP4 在 CPU 上怎么算

**格式（读码确认）**：CPU 直接读 host bank 的**原生 NVFP4 布局**（与 GPU 流式取数的 bank 同一份内存，零重打包）：
- bank schema：`moe/offload_cache.py:65-72` — `gate_up_packed [E,2I,H/2] u8`（e2m1 两码/字节，低半字节在前）、`gate_up_scale [E,2I,H/16]` fp8-e4m3（每 16 元素一个块尺度）、`gate_up_global [E,2I]` fp16（每输出行的全局尺度）；down 同理。形状断言在 `moe/cpu_executor.py:381-394`。
- 每专家字节数公式：`moe/offload_cache.py:107` — `nvfp4: 2*I*(H//2 + H//16 + 2) + H*(I//2 + I//16 + 2)`（packed + scale + global）。

**是否反量化 / 怎么算（读码确认）**：不整体反量化、不物化 fp 权重；两条路径：
1. **W4A16 忠实路径**（无 VNNI 时）：激活 bf16→fp32 精确拆分（偶/奇 K 两半，`deinterleave_bf16_f32`，`cpu_moe_ext.cpp:1051-1056`），K-loop 内查表反量化 `w = E2M1[code] * e4m3[scale] * global`（`cpu_moe_ext.cpp:216-219`、LUT `222-223`/`257-264`），fp32 累加；块尺度按 16 元素块在块和外乘（`dot_nvfp4_scalar` `271-290`，`acc += bs*bsum`；AVX-512 版 `344-374`，AVX2 版 `387-405`）。
2. **W4A8 VNNI 路径**（Ice Lake 默认走这条，见 Q3）：权重半字节经 PSHUFB LUT 转成 **int8**（e2m1×2 精确表 `kE2M1x2`，`cpu_moe_ext.cpp:225-228`；256-bit `nvfp4_decode_block_i8` `411-416`；512-bit `_mm512_shuffle_epi8` 在 `482-510`），与 int8 激活做 **整数点积 VPDPBUSD**（`_mm512_dpbusd_epi32`，`cpu_moe_ext.cpp:499`；u8×s8 用 `|w|*(sign(w)*a)` 符号技巧，`494-498`），块尺度 `(e4m3[wscale] * asb[act])` 在 fp32 侧乘回（`507-509`），结尾乘 `0.5*global` 折回 ×2（`563`）。

**结论**：NVFP4 在 CPU 上是「查表（LUT）→ int8 或 fp32 → 逐块点积」；不是逐块转 fp32 物化。

## Q3 激活值处理 / 指令集

**读码确认**：
- 输入激活（bf16）：每 token 一次、在**提交者线程上单线程**做完（`submit()`，`cpu_moe_ext.cpp:1911-1941`）：nvfp4/ds_fp4 先 `deinterleave_bf16_f32` 成 fp32 偶/奇两半（`1934-1936`）；若 `use_vnni`，再 `quant_i8_pg16` 量化为 **per-16 块 int8**（块内 amax/127 对称量化，`cpu_moe_ext.cpp:1459-1477`，布局 [even(8),odd(8)]）。**不是 q8_K**（未找到 q8_K；q4_0 格式才用 llama.cpp 的 Q8_0 per-32，见 `1438-1454`）。
- 中间激活 g（gate_up 输出过激活函数后，bf16 存）：pass1 与 pass2 之间由 `prep_g_row` 同样做 deinterleave(+int8 量化)（`cpu_moe_ext.cpp:1799-1813`），在两次屏障之间由 worker 分摊（`run_task_body` `1854-1860`）。
- ds_fp4 额外做 FP8-e4m3 往返（`fp8_roundtrip_bf16`，`1060-1073`；可移到 GPU 做，`cpu_executor.py:303-316`）。

**指令集选择（读码确认）**：构造期一次性 `pick_isa()`（`cpu_moe_ext.cpp:679-700`），档位 scalar→AVX2+FMA→AVX512F→AVX512-BF16（bf16 格式用 `dpbf16`，`152-171`）；NVFP4 额外独立探测 `avxvnni`（256-bit，`727-735`）与 `avx512vnni`（512-bit，`742-752`），选中则 `use_vnni=true`（`1396-1397`）。可用 env 封顶/禁用：`FREETOKEN_CPU_MOE_ISA`、`FREETOKEN_CPU_MOE_SCALAR`、`FREETOKEN_CPU_MOE_NO_VNNI`、`FREETOKEN_CPU_MOE_NO_AVX512VNNI`（`678-751`）。软预取距离 env：`FREETOKEN_CPU_MOE_PF_BLOCKS`（`466-472`，默认 min(4KB, 2 行)）。
- **推断**：Xeon Silver 4310（Ice Lake）有 AVX-512F/BW/VNNI、无 AVX512-BF16 → 档位 `avx512`，NVFP4 走 `dot_nvfp4_i8_avx512vnni`（W4A8）；bf16 格式走 `dot_avx512f`（无 dpbf16）。

## Q4 线程模型（本批最优先）

**结构（读码确认）**：每进程一个持久池 `std::vector<std::thread> workers`（`cpu_moe_ext.cpp:1287`，构造时 spawn `1431-1432`），Python 侧 `CpuMoeExecutor` 持有（`moe/cpu_executor.py:144-323`）。默认线程数 = 物理核数（每物理核取一个逻辑 CPU，SMT 兄弟去重，`cpu_executor.py:92-116` `physical_core_cpus`、`119-141` `resolve_threads_and_affinity`）；`--moe-cpu-threads` 显式指定（`engine/config.py:53-55`）。绑核：worker `pin_self` → `pthread_setaffinity_np`（`cpu_moe_ext.cpp:1527-1538`）；flag-sync 协调线程在 auto 模式下独占最后一个物理核（workers 减 1，`cpu_executor.py:221-228`；C++ 侧 `2006-2013`）。torch intra-op 线程数被压到剩余空闲核（`cpu_executor.py:250-257`）。

**每层每步的睡眠/唤醒/屏障计数（读码确认，nvfp4 路径，`needs_di=true`）**：
- 工作线程：**每层 1 次 CV 睡眠/唤醒**（`worker_loop`，`cpu_moe_ext.cpp:1874-1876` `task_cv.wait`），醒后进入 `run_task_body`（`1843-1867`）：pass1 抢 tile → **屏障 1（自旋）**（`1850`）→ prep 阶段（deinterleave/int8 量化）→ **屏障 2（自旋）**（`1860`）→ pass2 抢 tile。bf16 格式无 prep，只有 1 次屏障。
- 屏障实现：sense-reversing 集中式**自旋屏障**（`cpu_moe_ext.cpp:1568-1580`）：非末位 worker `while (bar_sense != local) _mm_pause();` 纯自旋；末位 worker 翻 sense 放行。注释明确"oversubscribed 时自旋屏障急剧劣化"（`1089-1103`）。
- 协调/提交线程：**也睡眠**。flag 路径下协调线程在 `submit()` 后调 `sync()`，`sync_cv.wait`（`1964-1968`）睡到全部 worker 完成；完成信号由最后完工的 worker 发（`done_count` 到达 `num_threads` → `completed=gen` → `sync_cv.notify_all`，`1882-1888`）。
- 唤醒到开算之间的步骤（提交者视角，`submit()` `1892-1962`）：算 tile 总数 → **单线程预处理**（nvfp4：每 token deinterleave H 维 + int8 per-16 量化，标量循环，`1911-1941`）→ 拿 `task_mtx`、设 `cur_task`、`++cur_gen` → `task_cv.notify_all()`（`1955-1961`）。worker 醒后还要过同一把 mutex 读 task（`1874-1880`），然后 `fetch_add` 抢 tile 才算第一行点积。

**任务切分（读码确认）**：按**输出行 tile** 切，不按专家切。`IBLK=HBLK=32`（`cpu_moe_ext.cpp:1104-1105`）；pass1 tile = (token, route k, 32 个中间行)（`1582-1637`，`p1_total = tokens*top_k*n_iblk`，`1900`）；pass2 tile = (token, 32 个隐藏行)，内部循环该 token 的全部 top_k 路由（`1639-1678`）。worker 用原子计数 `p1_next/p2_next/prt_next` work-stealing（`1846/1856/1863`）。注释明确 deferred：AMX（M=1 GEMV 用不上）、bs>1 的专家去重、NUMA K 维切分（`1097-1103`）。

**每层固定开销构成（读码确认 + D08 实测）**：D2H 三次 copy + GPU 前端 memop 提交（或 host-func ~30-50µs/次×2，`cpu_executor.py:32-50`）→ 协调线程轮询发现 → `submit()` 单线程预处理（nvfp4 的 deinterleave+int8 量化在关键路径上）→ mutex+notify_all 唤醒 → worker futex 唤醒延迟 → 2 次自旋屏障（等待最慢 worker 的偏斜）→ 完工 notify → 协调线程醒、写 done → GPU 前端 WAIT 放行 → H2D 拷贝。D08 复核实测：每层 CPU 任务 = **0.207 ms 固定 + 0.084 ms/专家**（`freetoken/plan/02_开发任务/D08_hybrid执行器诊断埋点.md` 顶部 2026-10-11 批注）。

**D08 对照（Strata 线程池移植进度）**：
- D08 计划（`D08_hybrid执行器诊断埋点.md:18-23`）：移植 Strata `pool.cpp`（779 行，worker 空闲休眠、`_mm_pause` 短等后睡）替换 `cpu_moe_ext.cpp` 自旋屏障与绑核选择；NUMA membind 选项；不引入 Strata GGUF kernel。
- 已在发布版 481d3a7 中（读码确认存在，部分早于 D08）：任务派发本来就是 CV 睡眠（D08 交付记录原话"任务派发的原有条件变量……未改"，`D08_C1_交付记录_20261005.md:8`）；物理核优先 + SMT 去重（`cpu_executor.py:92-141`）；协调线程独占核（`221-228`）；协调线程空闲退避（50ms 热窗后递增至 2ms 睡眠，`cpu_moe_ext.cpp:2019-2085`）。
- D08 实验分支 `exp/e2d08`（提交 `dc78111`）做过、但**未进发布版**：两处相位屏障从自旋改成带 sense 谓词的 CV 睡眠（`D08_C1_交付记录_20261005.md:8`）、worker 服务计数/绑核诊断、`FT_DEV_HYB_TRACE` 每层 JSONL 计时。**佐证**：发布版快照中屏障仍是自旋（`cpu_moe_ext.cpp:1568-1580`），且全文搜不到 `FT_DEV_HYB_TRACE`/`hyb_trace`（未找到清单 #2）。D08 卡 2026-10-09 以"已测量、无收益"关闭，不追加移植（D08 文档第 7 行）。
- 仍缺（相对 Strata）：睡眠式相位屏障、NUMA membind 内建（交付记录"未闭合项"：`D08_C1_交付记录_20261005.md:72`，retry2 只能靠外部 `numactl --interleave=all`）、Strata 的可跳首核策略。

## Q5 内存布局与 NUMA

**读码确认**：
- host 专家 bank：每层每 bank 独立分配（`moe/offload_cache.py:596-601`、`set_bank_sources` `588-661`），默认 `HostResidency.PINNED` — pin-after-fill，填充后 `cudaHostRegister`（portable+mapped）（`moe/host_banks.py:130-144`，`kernel/pinned.py:48-49`）；也可 born-pinned `cudaHostAlloc`（`host_banks.py:82-115`）。超 pin 配额时 LOCKED（`mlock`，无 device 地址，只能 CPU 算；`host_banks.py:154-195` `_os_lock`）。split residency 由 engine 决定（`engine/engine.py:639-667`）。
- CPU 侧无独立布局：CPU kernel 直接读同一份 pinned bank（`cpu_executor.py:325-405` 只建 per-layer 指针表 `_make_table`，`cpu_moe_ext.cpp:1230-1232` `tbl_at`）。
- **NUMA：无内建感知**。C++ 注释明示"a single node is assumed……Multi-socket would split each expert's K dimension per node"且列为 deferred（`cpu_moe_ext.cpp:1102-1103`）。全包搜 `numa|mbind|set_mempolicy|interleave` 无相关实现（未找到清单 #1）。retry2 的 hybrid 服务靠**外部** `numactl --interleave=all` + `taskset -c 1,3-23,25,27-47` 前缀（`_src_snapshot/retry2/d08_d10_gpu_retry2_20261011/hybrid_service.py:21-28`）——即交错放置 + 每物理核一个逻辑 CPU，是启动器行为而非 FreeToken 代码。
- IO buffer（x/ids/w/y）与 ready/done/err 旗标：pinned（`cudaHostAlloc`，`cpu_executor.py:493-503`、`277-282`；`kernel/pinned.py:42-46`）。

## Q6 CPU 与 GPU 的并行与合并

**读码确认**（`_decode_hybrid`，`layers/moe.py:328-383`）：
1. `raw = topk_ids.clone()`；`ensure_experts_hybrid` 改写 `topk_ids`（347）。
2. `cpu_ids = where(on_gpu, -1, raw)`（352）；**先** `executor.decode_submit(...)`（353）把 CPU 任务踢出去 —— 注释即设计意图："kicked off before the GPU PCIe fetch + GEMM so the CPU overflow GEMV runs concurrently"（338-340）。
3. GPU 侧：`copy_missing()`（363，fused 单 launch 多 bank 拷贝，`offload_cache.py:1385-1399`）→ GPU grouped GEMV（370-379；CPU 路由的权重被置 0、slot clamp 到 0，`366-367`，保证每路由只算一次，`341-342`）。
4. `cpu_routed = executor.decode_sync(pending)`（382）；**合并：`return gpu_routed + cpu_routed`**（383，GPU 上 bf16 逐元素加）。
- 测量开关：`FREETOKEN_HYBRID_OVERLAP=0` 时把 `decode_sync` 提前到 GPU 工作之前，强制串行做 A/B（`layers/moe.py:26`、`355-359`）。

**隐藏状态搬运（读码确认，`cpu_executor.py`）**：D2H：`io["x"/"ids"/"w"].copy_(..., non_blocking=True)` 在当前 stream 上异步拷到 pinned（`570-572`）；提交：默认 **stream memory operations**（`cuStreamWriteValue64`：done=0、ready=1，`580-583`；C++ `cpu_moe_ext.cpp:646-657`），不可用时退回 `cudaLaunchHostFunc`（`584-586`，C++ `1970-1978`）。同步：GPU 前端 `cuStreamWaitValue64(done>=1)`（`594-599`；C++ `659-664`，不占 SM）或 host-func `sync_cb`（`600-602`，C++ `1975-1978`、`2106-2109`）。H2D：`out.copy_(io["y"], non_blocking=True)`（`604`）。无任何轮询 GPU；CPU 侧协调线程 busy-poll ready 旗标（见 Q4）。watchdog 线程兜底死协调线程（`cpu_executor.py:607-660`）。

## Q7 与 CUDA Graph 的关系

**读码确认**：decode 整步一张 CUDA Graph（`engine/graph.py:184-205` 按 batch size 捕获整个 `model.forward()`；`replay` 整步重放，`214-220`；仅 decode 且 bs ≤ 上限可用，`211-212`）。hybrid **不打断图、不走 eager**：
- 路由切分 device-side 定形状（`offload_cache.py:1221-1222`）；CPU submit/sync 以 host node 或 stream memop 形式被捕获进图（`cpu_executor.py:4-15`、`536-539`；memop 的 WAIT 立即数是常量，重放安全，`cpu_moe_ext.cpp:630-631`、`cpu_executor.py:264-272`）。每 (layer, bs) 一个旗标槽（容量 `num_layers*16`，`cpu_executor.py:55`、`273-286`）。
- 每层图内有：3×D2H memcpy 节点 + submit（memop×2 或 host-func）+ GPU fetch/GEMM 节点 + sync（memop WAIT 或 host-func）+ 1×H2D memcpy + 加法节点。**没有 host 可见的逐层同步**（GPU 前端等待而已）。捕获前的 eager warmup 负责物化 pinned buffer/task 指针（`cpu_executor.py:11-15`）。
- 统计：`collect_stats` 的累加也被捕进图（`offload_cache.py:243-244`）；`collect_decode_freq` 则不图安全（`266-269`）。D0 timeline/route trace 会整体禁用 CUDA graph（`engine/graph.py:124-127`）。

## Q8 缓存容量与显存预算

**读码确认**：
- GPU 专家槽位缓存：每 bank 一个统一池 `[cache_size, *row]`（`offload_cache.py:653-657`）。`moe_cache_size` 默认 0 需显式/`--moe-cache-auto`（`engine/config.py:42-44`；缺省报错 `engine/engine.py:42-46`）。
- auto 求解：`engine/engine.py:603-628` → `engine/cache_budget.py:98-133` `resolve_moe_cache_auto` → `plan_cache_budget`（`48-95`）：预算 = `memory_ratio(0.9)×加载前基线空闲 − 权重 − 固定缓存`（`31-38`）；**MoE 优先**：先扣 KV 保底（`kv_reserve_tokens` 默认 8192，`engine/config.py:45`），专家槽位贪婪吃满剩余，上限 `min(total_experts, kernel slot cap)`，下限 `2*num_experts`（prefill overlap 借用前 2E 槽）或 `num_experts`；KV 页吃剩下的（`cache_budget.py:69-84`）。每槽字节 = 各 bank 行字节之和（`cache_budget.py:17-28`）。
- 本场景 ~2700 槽的佐证：retry2 hybrid 服务把实测 `moe_cache_size` 与 2700 比 ±5%（`hybrid_service.py:154-164`），并认定 num_experts=512（同段 fraction 模式注释）。2700 本身是 auto 解出的结果，不是硬编码（推断）。
- `--moe-strategy cpu` 特例：槽缓存固定 2*num_experts（只做 prefill 双缓冲）（`engine/engine.py:2004-2017`）。
- KV 缓存：paged bf16 池（DSV4 池注释：fp8/fp4 是原地 round-trip，池本身 bf16，`kvcache/dsv4_paged_pool.py:11,164`）；页数 `solve_num_pages` 来自同一预算（`engine/engine.py:423-428`、`_startup_kv_budget` `72-76`）。未找到 KV 独立量化预算开关（未找到清单 #4）。

## Q9 两路/批量（B=2）时 CPU 端是否合并同专家计算

**读码确认：不合并，按 (token, route) 独立重复读权重。** pass1 tile 的索引含 `tok` 和 `k`（`cpu_moe_ext.cpp:1591-1597`），两个 token 命中同一专家会各自把该专家权重流一遍；代码注释明确把"expert dedup for bs>1（每个不同专家只读一次、对其 token 做 GEMM）"列为 deferred，理由是"decode batches here are tiny (<=4)"（`cpu_moe_ext.cpp:1100-1101`）。两路共享的是**每次任务的固定开销**（一次唤醒 + 两次屏障覆盖整个 batch 的所有 token/tile），D08 复核："两路共享这份开销，诊断模式下两路步长只比单路长 13%"（D08 文档顶部批注）。

## Q10 数值一致性：hybrid 与 offload 为何不逐位一致

**读码确认的差异来源**（CPU 头注释自述"FP32-accumulate；中间值存 bf16 以匹配 GPU decode 路径"，`cpu_moe_ext.cpp:14-16`，但只是"匹配精度级"，不是逐位）：
1. **块尺度施加顺序不同**（即使非 VNNI）：GPU Triton GEMV 把 `lut*scale` 逐元素乘进权重再求和（`kernel/triton/nvfp4_fused_moe.py:114-132`），CPU 是 16 元素块内先裸点积再乘块尺度（`cpu_moe_ext.cpp:287` `acc += bs*bsum`）——fp32 舍入序不同。
2. **激活量化**（Ice Lake 默认路径）：CPU VNNI 路径把激活量成 int8/per-16（`quant_i8_pg16`，`cpu_moe_ext.cpp:1459-1477`），GPU 用 bf16 激活（`nvfp4_fused_moe.py:129-130`）——这是真实量化误差，不只是舍入。
3. **激活前舍入点不同**：GPU 把 gate/up 的 GEMM 结果先写 bf16（`ic1`，`moe/fused_nvfp4.py:188-194`）再过激活；CPU 在 fp32 上直接做 silu/gelu（`act_apply`，`cpu_moe_ext.cpp:84-92`）然后一次性 `f32_to_bf16`（`1632-1634`）。
4. **top_k 归约路径不同**：纯 offload 由 `moe_sum_reduce` 对全部 top_k 在 fp32 累加、一次写 bf16（`kernel/triton/fused_moe.py:142-153`）；hybrid 里 CPU 部分和先 `f32_to_bf16` 落 pinned（`cpu_moe_ext.cpp:1676`），H2D 后再与 GPU 部分和做 **bf16 逐元素加**（`layers/moe.py:383`）——多一次 bf16 舍入 + 一次 bf16 加法。
5. 逐位一致从来不是验收标准：D08 的 G3 门要求的是"不设开关时 `cold_eq.py` 全文逐字相同"（生成文本级，`D08_hybrid执行器诊断埋点.md:36,77`）。

---

## 调用链（router → 未命中决策 → CPU 派发 → 合并 → 写回）

decode 一步、一个 MoE 层（hybrid、flag-sync 默认路径）：

| 阶段 | 位置 |
|---|---|
| router 打分/选专家 | `layers/moe.py:241-246`（`fused_topk`）；外部路由模型 `layers/moe.py:210-234` |
| 层入口分发 | `layers/moe.py:276-306`（`_decode_routed` → `_decode_hybrid`） |
| 命中/取数/CPU 标记（GPU kernel） | `moe/offload_cache.py:1213-1232` → `moe/offload_kernels.py:43-60, 97-125` → `_ensure_experts_hybrid_kernel` `offload_kernels.py:291-410` |
| CPU 路由集合生成 | `layers/moe.py:346-352`（`raw` clone、`on_gpu`、`cpu_ids`） |
| CPU 派发（提交） | `layers/moe.py:353` → `moe/cpu_executor.py:543-587`（D2H `570-572`；memop `577-583` / host-func `584-586`；task 创建 `505-526`）→ C++ `cpu_moe_ext.cpp:646-657`（memop）→ 协调线程 `2019-2060` → `submit()` `1892-1962` → 唤醒 worker `worker_loop` `1869-1890` |
| CPU 计算 | `run_task_body` `cpu_moe_ext.cpp:1843-1867`（`do_pass1` `1582-1637` → 屏障 `1568-1580` → `prep_g_row` `1799-1813` → 屏障 → `do_pass2` `1639-1678`） |
| GPU 取数 | `layers/moe.py:363` → `moe/offload_cache.py:1369-1411` `copy_missing`（fused：`kernel/fast_index_copy`，`1385-1399`） |
| GPU 专家 GEMM | `layers/moe.py:370-379` → `_expert_gemm` `450-471` → `moe/fused_nvfp4.py:161-202`（GEMV `kernel/triton/nvfp4_fused_moe.py:90-142`） |
| CPU 同步 + 结果 H2D | `layers/moe.py:382` → `moe/cpu_executor.py:589-605`（memop WAIT `594-599` / host-func `600-602`；H2D `604`） |
| 合并写回 | `layers/moe.py:383`（`gpu_routed + cpu_routed`，bf16）；随后 `_maybe_all_reduce`（TP 时）`layers/moe.py:95-98, 208` |

executor 建立：`engine/engine.py:752-753` → `_init_cpu_moe_executor` `789-823` → `cache.set_cpu_executor`（`moe/offload_cache.py:851-861`）。

## 微基准入口（只调查，未执行）

**PYBIND11 绑定**（`freetoken.kernel._cpu_moe`，`cpu_moe_ext.cpp:2114-2159`）：
- `CpuMoeExecutor(num_threads, num_layers, num_experts, top_k, hidden_size, inter_size, max_tokens, activation_id, apply_router_weight_on_input, weight_format, gate_up_ptr, down_ptr, gate_up_scale_ptr, gate_up_global_ptr, down_scale_ptr, down_global_ptr, gate_up_bias_ptr, down_bias_ptr, swiglu_alpha, swiglu_limit, core_ids)` — 指针参数是 per-layer int64 指针表的地址（`cpu_moe_ext.cpp:1225-1232`）。
- 方法：`create_task(layer_id, num_tokens, x_ptr, ids_ptr, w_ptr, y_ptr) -> int`（`2129-2131`）；`run_task(task)`（GIL released，eager 同步跑完，`2136-2137`、C++ `2096-2100`）；`submit_with_cuda_stream(stream, task)` / `sync_with_cuda_stream(stream, task)`（`2132-2135`）；`register_flag_task(slot, task)`、`flag_served_count(slot)`、`start_flag_coordinator(ready_ptr, done_ptr, num_slots, pin_core)`、`set_input_prequant(value)`、`isa_name()`（`2138-2147`）。
- 模块函数：`memops_probe(stream, scratch_addr)`、`memop_submit(stream, done_addr, ready_addr, slot)`、`memop_sync(stream, done_addr, slot)`、`max_generic_act_id()`（`2148-2159`）。

**现成 bench 入口**：
- `ft bench bw`（`cli.py:76-89` → `moe/benchbw.py:691-731` `run_benchbw`/`main`）。CPU MoE 带宽：`moe/benchbw.py:506-535` `measure_cpu_moe_bw(fmt, wl, iters=64, num_threads=0, isas=None)`；内部 `_build_cpu_moe_executor`（`449-464`，用 `SimpleNamespace` 假 cache + 合成 pinned bank `_cpu_moe_bank_sources` `327-383`）、`_cpu_moe_step_fns`（`467-486`：bs=1，旋转 expert id 窗口保证 DRAM 区间）、`_time_cpu_moe`（`489-503`，median）。overlap 对测：`measure_overlap_bw`（`538-595`）。**注意需要 CUDA**（executor 构造传 `device=torch.device("cuda")`，且 flag-sync 会探测 stream memop）。
- 取数比例读取（torch-free）：`moe/bench_profile.py:156-191` `load_hybrid_fetch_fraction(quant_format, gpu_name, path, gpu_uuid)`；profile 路径 `$XDG_CACHE_HOME/freetoken/benchbw/<gpu-uuid>.json`（`39-46`），`FREETOKEN_BENCHBW_PATH` 可覆盖（`88`）。

**能否纯 CPU 测（推断，基于读码）**：
- (a) 空任务派发往返延迟：可以。构造 `CpuMoeExecutor` 时传 `device=torch.device("cpu")` 即可跳过 flag-sync（`cpu_executor.py:206` `self._flag_sync = _FLAG_SYNC and device.type == "cuda"`，不触发 memops 探测），然后 `ex._ext.run_task(task)` 循环计时。空任务 = `io["ids"]` 全填 -1（C++ 在 `cpu_moe_ext.cpp:1596` 跳过 `e<0`，tile 仍被分发 → 测到的就是 唤醒+2 屏障+完工 的纯开销）。线程数经 `num_threads=1/12/24` 传入（`benchbw.py:459-463` 同签名）。**环境线索**：需要 importable 的 `freetoken` 包（`PYTHONPATH=python`）+ 已编译的 `freetoken/kernel/_cpu_moe*.so`；构建命令见 `D08_C1_交付记录_20261005.md:32-37`（`MAX_JOBS=2 CUDA_VISIBLE_DEVICES='' python setup.py build_ext --build-lib python`）。注意该 .so 链 CUDA runtime（交付记录 `46-48` 行），import 阶段需要 CUDA-enabled torch 与 CUDA_HOME；`run_task` 本身不碰 CUDA API。
- (b) 1/3/10 个专家批耗时：可以。bs=1 下 CPU 每步算 `top_k` 个专家（无去重），所以分别构造 `top_k=1/3/10` 的 executor（或同一 top_k 下把多余 route 填 -1），配合 `set_ids` 旋转窗口（仿 `benchbw.py:467-503`）即可得到每专家边际成本 vs 固定开销（即 D08 复核的 0.207ms + 0.084ms/专家 的测法）。
- ISA A/B：`FREETOKEN_CPU_MOE_ISA`/`_NO_VNNI`/`_NO_AVX512VNNI`（`cpu_moe_ext.cpp:678-752`）；预取距离 `FREETOKEN_CPU_MOE_PF_BLOCKS`（`466-472`）。
- 测试脚本（仓库内有、快照未含）：`tests/moe/test_cpu_affinity.py`、`tests/moe/test_cpu_moe_pool_native.py`、`tests/moe/test_dsfp4_prequant.py`、`tests/test_offload_lru_kernels.py`（D08 交付记录与 `offload_kernels.py:131-135` 提及）。

## 未找到清单

1. **NUMA 内存放置 API**（mbind/set_mempolicy/libnuma 调用、专家 bank 交错/节点绑定）：全快照搜 `numa|mbind|set_mempolicy|interleave` 无果（唯一 libnuma 命中是 `attention/fa.py:178` 的安装提示，无关）。仅有 deferred 注释 `cpu_moe_ext.cpp:1102-1103`；retry2 靠外部 `numactl --interleave=all`（`hybrid_service.py:28`）。
2. **`FT_DEV_HYB_TRACE` / `hyb_trace` / `worker_pool_diagnostics`**：发布版快照全文搜索无果 → D08 的每层计时埋点与 CV 屏障移植只在 `exp/e2d08` 分支（`D08_C1_交付记录_20261005.md`），未进 481d3a7。
3. **专家去重 / 按专家切任务 / AMX**：未实现，注释明列 deferred（`cpu_moe_ext.cpp:1097-1103`）。
4. **KV 缓存独立量化预算开关**：未找到；KV 池 bf16（`kvcache/dsv4_paged_pool.py:11,164`），页数与 MoE 槽位共用同一预算求解（`engine/cache_budget.py:48-95`）。
5. **q8_K 激活量化**：未找到（搜 `q8_K|q8k` 无果）；nvfp4 W4A8 用自研 per-16 int8（`quant_i8_pg16`），q4_0 用 Q8_0 per-32（`quant_q8_0`）。
6. **CPU 侧单独的权重布局/重打包**：不存在——CPU 直接读与 GPU 取数相同的 pinned bank（`cpu_executor.py:325-405` 只建指针表）。
