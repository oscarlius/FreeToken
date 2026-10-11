# Q1–Q10 对照：FreeToken 481d3a7 vs Strata v0.1.41（"CPU 计算未命中专家"路径）

- 调研日期：2026-10-11，只读。代码版本与路径前缀见 CODE_MAP.md 头部。
- 每条结论标注「读码确认」或「推断」；证据位置列给两侧 `文件:行号`。
- 微基准数据见 MICROBENCH.md（本文件引用其数值时标注「微基准」）。
- 背景修正（按补充 1）："每专家 0.20–0.24 对 0.071 ms、差 3 倍"的说法已作废；现行模型为
  `t_step ≈ S_GPU + Σ层 max(G + f·t_P, O_C + (n−f)·t_C)`，差距主因是每层固定开销 O_C 与 GPU 串行部分。

---

## Q1 每层每步，一个专家在 GPU 算还是 CPU 算，由谁决定？

**FreeToken**：决策在 **GPU 上**、由单 program Triton kernel `_ensure_experts_hybrid_kernel` 完成（读码确认）。
命中判定查 GPU 上的 [L,E] 槽位表 `slot_for_id`；取数数量由 `max_fetch` 上限或 `fetch_frac_q16`（Q16 定点比例，kernel 内按当层 miss 数现算）封顶；溢出 miss 的 id 被原地改写为 -1 交给 CPU。取哪些 miss 默认按 LRU 最近活跃优先。Python 只消费结论（`on_gpu = topk_ids >= 0`）。比例来自 `ft bench bw` profile 的 PCIe/CPU 带宽比（engine auto 解析）；无 profile 时固定 cap=1。

**Strata**：决策在 **host 侧 C++** `expert_pool_dispatch_multi`（读码确认）。窗口内路由按序去重（上限 128 条），查 host 驻留表 `host_res`：slot≥0 → GPU；其余按 miss_rank 排序，最后 `(nmiss*pcie_num)>>8` 个且 pinned 可取的走 PCIe DMA，剩下全归 CPU。S1 `--pcie-frac 0` → 全部 miss 归 CPU；`--adapt-swaps 0` → 驻留表整 run 静止（启动时按 `--expert-profile` 顺序灌入）。默认配置（native pack）pcie-frac 约 0.55（读码确认于 generate.cpp:2458-2470）。

**差异对速度的可能影响**：FT 的 device-side 决策零 host 往返、定形状、CUDA-graph 安全，且 LRU 取数能随工作集漂移；Strata 的 host 决策本身不在关键路径上（收铃后顺手做），配合"计划先行发布"让 GPU 先算命中组。两者决策成本都不大；差异主要在**决策后**的执行结构（见 Q4/Q6）。（推断）

**证据位置**：
- FT：`python/freetoken/moe/offload_kernels.py:291-410`（kernel）、`:341-343`（命中）、`:345-355`（比例现算）、`:364-368,406-410`（BY_RECENCY）、`:400-404`（改写 -1）；`python/freetoken/layers/moe.py:347-352`；`python/freetoken/engine/engine.py:758-787`（auto 解析）；`python/freetoken/moe/bench_profile.py:156-191`。
- Strata：`src/core/expert_source.cpp:3105`、`:3155-3164`（去重）、`:3177-3182`（驻留表）、`:3166-3167,3191-3199`（PCIe 份额）、`:3175`（默认 kind -1）；`src/program/generate.cpp:4674-4688`（启动灌入）、`:11544,11586-11678`（adapt）、`:7377`（pcie_num 换算）、`:2458-2470`（默认 0.55）。

## Q2 CPU 读到内存里的专家是什么格式？

**FreeToken**：CPU 直接读 host bank 的**原生 NVFP4**（与 GPU 流式取数同一份 pinned 内存，零重打包）（读码确认）：packed e2m1（2 码/字节）+ fp8-e4m3 每 16 元素块尺度 + fp16 每行全局尺度；每专家字节 = `2*I*(H//2+H//16+2) + H*(I//2+I//16+2)`（H=2560、I=640 时约 2.77 MB）。**不整体反量化**：Ice Lake 默认走 **W4A8**——权重半字节经 PSHUFB LUT 转 int8，与 per-16 int8 激活做 VPDPBUSD 整数点积，块尺度在 fp32 侧按 16 元素块乘回；无 VNNI 时退化 fp32 查表逐块点积。

**Strata**：CPU 读 pack 的**原生 IQ 系 GGUF blob**（读码确认）：S1 实测模型为混合量化（gguf 头读码确认：gate/up 有 Q3_K/IQ2_S 等、down 有 IQ4_NL/Q2_0(42)，逐层不同）；blob 布局 = gate 行 + up 行 + down 行，`native_fmt` 算偏移。**不反量化**：IQ3_S 每 256 值一块 110 B，9-bit 索引查 iq3s_grid 码表得 int8，64-bit 符号掩码取负，`_mm512_maddubs/madd_epi16` 全整数点积，每 256 值块才一次 fp32 FMA。iq3_s/iq4_nl 组合每专家 2.22 MB（微基准实测输出）。

**差异对速度的可能影响**：Strata 每专家字节少约 20–26%（1.9–2.2 vs 2.77 MB），DRAM 流式读取时间同比少；且 IQ 整数主干每 256 值才一次 fp32 操作，FT 的 NVFP4-W4A8 每 16 元素一次块尺度乘法、激活还要先做 per-16 量化——单核每字节耗时微基准实测 FT 0.373 ms/MB、Strata 0.253–0.296 ms/MB，差 25–32%（微基准）。

**证据位置**：
- FT：`python/freetoken/moe/offload_cache.py:65-72,107`（bank schema/字节公式）；`python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp:216-228,411-416,482-510,563`（LUT/VNNI 路径）、`:271-290`（标量块外乘尺度）、`:1396-1397`（use_vnni 选定）。
- Strata：`src/kernels/cpu/iq_avx512.cpp:130-186`（IQ3_S 块布局与 row_dot）；`src/kernels/cpu/native_expert.cpp:46-83`（native_fmt）；`src/kernels/cpu/expert_layout.cpp:370-476`（native_experts.txt 读取）。

## Q3 激活值怎么处理？

**FreeToken**：不是 q8_K。bf16 激活每 token 一次：nvfp4 路径先 `deinterleave_bf16_f32` 拆偶/奇两半，VNNI 时再用自研 `quant_i8_pg16` 量化成 **per-16 块 int8**（块内 amax/127 对称）——且输入激活的这一步在**提交者线程单线程**做完才唤醒 worker（读码确认）。中间激活 g 的同类预处理在两次屏障之间由 worker 分摊。指令集：构造期 `pick_isa()` 一次选定（scalar→AVX2→AVX512F→AVX512-BF16；NVFP4 另测 AVX-VNNI/AVX512-VNNI）；Ice Lake 实测选中 `avx512f+avx512vnni(nvfp4-w4a8)`（微基准 isa_name 输出）。可用 `FREETOKEN_CPU_MOE_ISA` 等 env 封顶。

**Strata**：激活量化成 **ggml q8_K**（per-block int8），优先 AVX2 量化器 `q8k_quant_avx2`，回退 ggml `from_float`（读码确认）；量化在池相位之间由 host 串行做（读码确认）。点积用 `_mm512_maddubs_epi16`/`_mm512_madd_epi16`（AVX-512 VNNI 系指令）；ISA 分发 AVX-512→AVX2→ggml vec_dot 兜底。多 token 核起用阈值 `native_gu_mt_min`（默认 2，见 Q10）。

**差异对速度的可能影响**：两边激活都是 int8 整数点积路线，量级相当；FT 的 per-16 量化粒度更细（精度更好、量化本身更贵且在关键路径上单线程做），Strata q8_K 每 256 值块一次尺度、量化器独立 SIMD 化。固定开销层面 FT 更吃亏（见 Q4/O_C）。（部分推断：量化耗时占比未单独计时）

**证据位置**：
- FT：`cpu_moe_ext.cpp:1051-1056`（deinterleave）、`:1459-1477`（quant_i8_pg16）、`:1911-1941`（提交者单线程预处理）、`:1799-1813,1854-1860`（g 行 worker 分摊）、`:679-752`（ISA 探测）。
- Strata：`src/kernels/cpu/native_expert.cpp:90-104`（q8k_quant_avx2）、`:125-206`（ISA 分发）、`:106-123`（mt_min）；`src/kernels/cpu/iq_avx512.cpp:155-186`；`src/kernels/cpu/pool.cpp:772-775`（host 量化）。

## Q4 线程模型（首要问题）

**FreeToken**（读码确认，除注明外）：
- 结构：每进程一个持久池，worker 数默认 = 物理核数（每物理核一个逻辑 CPU，SMT 去重），`pthread_setaffinity_np` 绑核；flag-sync 协调线程独占最后一个物理核（workers 减 1）。
- 睡眠/唤醒计数（每层每步，nvfp4 路径）：worker **1 次 CV 睡眠/唤醒**（`task_cv.wait`）→ pass1 → **屏障 1（纯自旋）** → prep（worker 分摊）→ **屏障 2（纯自旋）** → pass2 → 末位 worker `sync_cv.notify_all` 完工。**协调线程也睡眠**（submit 后睡 `sync_cv`）。
- 屏障实现：sense-reversing 集中式**自旋**屏障（非末位 worker `while(...) _mm_pause()`）。
- 唤醒到开算的步骤：协调线程轮询发现 ready → `submit()` 关键路径上**单线程**做激活 deinterleave+per-16 int8 量化 → 拿 mutex 设 task → `notify_all` → worker 醒后过同一 mutex 读 task → 原子计数抢 tile 才算第一行。
- 任务切分：按**输出行 tile**（IBLK=HBLK=32），pass1 tile=(token,route k,32 中间行)、pass2 tile=(token,32 隐藏行)；**不按专家切、B>1 不去重**（代码注释明列 deferred：AMX、bs>1 去重、NUMA K 切分）。
- 每层固定开销构成：D2H×3 + memop 提交（或 host-func 30-50µs×2）+ 协调轮询 + 单线程预处理 + CV 唤醒 + 2 自旋屏障偏斜 + 完工通知 + GPU 前端 WAIT + H2D。D08 实测复核：每层 = **0.207 ms 固定 + 0.084 ms/专家**。本次合成微基准：纯池内往返下限 0.075 ms（24 线程空任务）+ 0.072 ms/专家斜率（微基准）。
- D08 移植进度：CV 睡眠式派发、物理核优先+SMT 去重、协调核独占、协调空闲退避**已在发布版**；**睡眠式相位屏障只在 exp/e2d08 分支（dc78111），未进 481d3a7**（发布版屏障仍自旋、快照搜不到 FT_DEV_HYB_TRACE）；NUMA membind 内建未闭合。

**Strata**（读码确认，除注明外）：
- 结构：worker = 每物理核一个（sysfs 拓扑探测、剔 SMT 兄弟），**host 让出自己占的第一个物理核**，pthread 绑核；混合 P/E 核默认 p_cores-1。
- 唤醒：worker 在 `epoch_` 上 `_mm_pause` **自旋**（每 1024 次 pause 看一次时钟），超过 `spin_before_sleep_`（env `STRATA_POOL_SPIN_US` 覆盖；默认常量 kSpinBeforeSleep 在 pool.hpp，**快照缺该头文件，默认值未找到**）才 mutex+CV 睡眠；publish = `epoch_++` + sleepers>0 时 notify_all。
- **无屏障库**：行空间按任务静态等分，host 自旋 `wait_parked`/`wait_done`（带 kStall 看门狗）。**host 自己也经同一 `head_` 计数器抢任务算**。
- 每层每步：2 次 publish（phase 5=gate/up、phase 6=down）+ 每 phase `wait_parked→begin_batch→(host drain)→wait_done→wait_parked`；自旋窗口内 worker **零睡眠**；两 phase 间 host 串行做 SwiGLU 后激活量化。
- 任务切分：每层两相位、phase 内把"所有专家 × 行"空间静态等分（一个任务可跨专家边界），任务数 ≈ 3×(worker+host)；专家多于 kMaxSplitMulti 时分批。

**差异对速度的可能影响**：Strata 在 decode 节奏下 worker 基本不睡眠（层间间隔 < 自旋窗口），消掉 CV 唤醒/睡眠往返与屏障偏斜；host 核不空转、多一路算力；静态行等分去掉 work-stealing 计数器竞争与"按 route 切"造成的同专家重复流。FT 的固定开销链（轮询→单线程预处理→CV 唤醒→2 自旋屏障→CV 完工）每层约 0.19–0.26 ms（retry2 标定，推断自算法研究），Strata 对应结构没有等价的串行段（推断；Strata 侧无现成池派发基准入口，见 MICROBENCH.md §偏差）。

**证据位置**：
- FT：`cpu_moe_ext.cpp:1287,1431-1432`（池 spawn）、`:1527-1538`（绑核）、`:1874-1876`（CV wait）、`:1568-1580`（自旋屏障）、`:1843-1867`（run_task_body）、`:1882-1888`（完工通知）、`:1892-1962`（submit）、`:1964-1968`（协调线程睡 sync_cv）、`:2019-2085`（协调退避）、`:1104-1105,1582-1678`（tile）、`:1097-1103`（deferred 注释）；`python/freetoken/moe/cpu_executor.py:92-141,221-228,250-257`。D08：`plan/02_开发任务/D08_hybrid执行器诊断埋点.md`（顶部批注）、`plan/02_开发任务/D08_C1_交付记录_20261005.md:8,72`。
- Strata：`src/kernels/cpu/pool.cpp:180-337,305-308`（拓扑/让核）、`:439-444`（spin env/P-E 核）、`:459-463` 与 `pool_affinity_linux.hpp:60-66`（绑核）、`:496-523`（自旋转睡眠）、`:476-487`（publish）、`:539-548,693,823-833`（host 抢任务）、`:564-606`（wait_parked/wait_done）、`:627-660,688-698,716-718,759-788`（相位/切分）。

## Q5 内存布局与 NUMA

**FreeToken**：host 专家 bank 每层独立分配，默认 pin-after-fill（`cudaHostRegister` portable+mapped），超配额退 LOCKED（mlock、无 device 地址）；**CPU 侧无单独布局**，直接读同一份 pinned bank（只建 per-layer 指针表）。**无内建 NUMA 感知**（代码注释明列 deferred："a single node is assumed... Multi-socket would split each expert's K dimension per node"）；retry2 靠**外部** `numactl --interleave=all taskset -c 1,3-23,25,27-47`（启动器行为）。（全部读码确认）

**Strata**：引擎代码内**同样没有** NUMA/mbind/hugepage 调用；S1 的交织+绑核完全靠外层 `numactl --interleave=all taskset -c 4-47`。锁页：RAM complement 区 `cudaHostAlloc(Mapped|Portable)`，失败退 malloc+`mlock`；Arena（含 y_miss mapped 行、门铃字）整体钉住建 device alias。（全部读码确认）

**差异对速度的可能影响**：两边 NUMA 都靠外部 numactl 交错，打平。Strata 多一层"mapped arena"让 GPU 图内直接读 CPU 结果（零 H2D 拷贝节点，见 Q6）；FT 需要显式 H2D memcpy 节点。（差异影响推断）

**证据位置**：
- FT：`python/freetoken/moe/host_banks.py:82-115,130-144,154-195`；`python/freetoken/moe/offload_cache.py:596-601`；`python/freetoken/moe/cpu_executor.py:325-405`；`cpu_moe_ext.cpp:1102-1103`；`_src_snapshot/retry2/d08_d10_gpu_retry2_20261011/hybrid_service.py:21-28`。
- Strata：`src/core/expert_source.cpp:2407-2468,2474-2529`（分步注册 STRATA_PIN_GUARD）、`:4072-4086,4154-4161`（arena）；`src/platform/memory.cpp:121-129`（mlock）；`_src_snapshot/strata_s1/argv.json:2-7`。

## Q6 CPU 与 GPU 怎么并行、怎么合并？

**FreeToken**（读码确认）：`_decode_hybrid` 先 `decode_submit` 把 CPU 任务踢出去（注释明示：先于 GPU 取数+GEMM 入队以重叠），GPU 侧随后 `copy_missing`（fused 单 launch）+ grouped GEMV（CPU 路由权重置 0）；每层 D2H 3 次（x/ids/w，异步进 pinned）+ 提交/同步用 **stream memory operations**（`cuStreamWriteValue64`/`cuStreamWaitValue64`，GPU 前端执行、不占 SM，图重放安全；不可用时退 host-func 30-50µs×2）+ H2D 1 次（y，异步）。GPU 无轮询；CPU 协调线程 busy-poll ready 旗标（空闲退避）。合并：H2D 后 `gpu_routed + cpu_routed`（GPU bf16 逐元素加）。

**Strata**（读码确认）：门铃（moe_route 末尾写 mapped 序号）→ host 收铃后 dispatch，**GPU 计划（命中组+PCIe 份额）先于 CPU 开工发布**（flagA/flagB），GPU 图内自旋核依次等 flagA→算 VRAM 命中组→等 flagB（PCIe DMA，S1 空）→等 m_flag_（CPU 行就绪）→ `copy_rows_from_mapped` 直接从 mapped pinned 读 CPU 行（**无显式 H2D 拷贝节点**）→ `moe_hit_add` 合并 → 整窗一次 `native_moe_combine_multi`。路由预读 RouterLookahead（host 用本层 x 预算下层 top-k 并暖页）只在 dj==0 且 `STRATA_FS_SLOTS` 开启时喂 Foresight 交换槽；**GPU 常驻命中不走预读**，S1 `--pcie-frac 0` 下预读无取数对象（读码确认 + 推断）。

**差异对速度的可能影响**：重叠思路两边对等（都先发布一侧再算另一侧）。差异在固定成本：FT 每层 3×D2H+1×H2D 拷贝节点 + memop 对；Strata 是图内自旋核等旗 + mapped 内存直读。FT 的 memop 设计不占 SM（比 Strata 自旋核更省 GPU），但每层多 4 个拷贝节点的 GPU 前端开销（推断，未单独计时）。

**证据位置**：
- FT：`python/freetoken/layers/moe.py:338-340,347-383`；`python/freetoken/moe/cpu_executor.py:543-605`（:570-572 D2H、:577-583 memop 提交、:594-599 memop WAIT、:600-602 host-func 退避、:604 H2D）；`cpu_moe_ext.cpp:646-664`（memop C++ 侧）、`:2019-2060`（协调轮询）。
- Strata：`src/core/layer.cpp:376-391`（门铃）；`src/core/verify.cpp:1449-1498`（图内等待与合并）、`:1971-2039`（host 收铃/写旗）、`:2168-2194`（fetch_dma+host-func）；`src/kernels/cuda/verify_kernels.cu:970,1151-1198`；RouterLookahead：`src/core/verify.cpp:1990-1994`、`src/program/generate.cpp:4959-4991`。

## Q7 与 CUDA Graph 的关系

**FreeToken**（读码确认）：decode 整步一张 CUDA Graph（按 batch size 捕获整个 forward）；hybrid **不打断图、不走 eager**——路由切分 device-side 定形状，submit/sync 以 stream memop（WAIT 立即数为常量，重放安全）或 host node 形式捕进图；每 (layer,bs) 一个旗标槽（容量 layers×16）。每层图内节点：3×D2H + 提交 + fetch/GEMM + WAIT + H2D + 加法。无 host 可见的逐层同步。

**Strata**（读码确认）：整个 verify 窗口捕获为一张图（token 级亦整图）；CPU 路径在图外，经 mapped 旗标 + 图内 `wait_flag_ge` **自旋核**（占 SM）握手；门铃序号取自 host 副本保证重放幂等。

**差异对速度的可能影响**：两边都不打断图，"hybrid 走 eager"的担心不成立（读码确认）。Strata 的自旋核占 SM 但在图内、无时序节点开销；FT 的 memop 不占 SM 但每层多 4 个 memcpy 节点 + 2 个 memop 节点的 GPU 前端开销。固定开销大头仍在 CPU 侧（Q4）。（影响推断）

**证据位置**：
- FT：`python/freetoken/engine/graph.py:184-205,211-212,214-220`；`python/freetoken/moe/cpu_executor.py:4-15,55,264-286,536-539`；`python/freetoken/moe/offload_cache.py:1221-1222`；`cpu_moe_ext.cpp:630-631`。
- Strata：`src/core/verify.cpp:1676-1769`；`src/core/session.cpp:836-908`；`src/core/layer.cpp:385-390`；`src/kernels/cuda/verify_kernels.cu:970,1151-1198`。

## Q8 缓存容量与显存预算

**FreeToken**（读码确认）：槽位数需显式或 `--moe-cache-auto`：预算 = `memory_ratio(0.9)×加载前基线空闲 − 权重 − 固定缓存`，**MoE 优先**——先扣 KV 保底（`kv_reserve_tokens`，生产 98304），专家槽位贪婪吃满剩余（上限 min(总专家数, kernel cap)、下限 2E/E），KV 页吃剩下的。~2,700 槽是 auto 解出的结果（retry2 以 ±5% 核对过），非硬编码。KV 池 bf16（paged），未找到 KV 独立量化预算开关。本机数据：2,700 槽 × 2.77 MB ≈ 7.3 GB（推断的算术）。

**Strata**（读码确认 + 日志佐证）：`--expert-cache auto`：`slots=(free_b − reserve − mtp − pipe − prefill)/max_blob`，再 min(slots, profile.size())，放不下 ×3/4 重试；S1 实得 **9,196 槽 / 17.45 GiB**（stderr.log:15）。省显存手段：**KV int8**（k/v int8+scale）、`--kv-resident 32768`（VRAM 只常驻 32K 窗，其余流式、权威 KV 在 pinned+mapped host）；文档给出 64K+ 上下文只留 32K 窗可让 1589→3872 个专家进 VRAM 的示例（DETAILS.md:78-80）。

**差异对速度的可能影响**：9,196 vs 2,700 槽 → 命中率 62–66%（S1 实测）vs FT 更低命中 → 每层 miss 数 n 不同，直接进 `(n−f)·t_C` 项。Strata 的优势来源：KV int8 + 32K 驻留窗把显存让给专家缓存；FT 的 KV 保底 98304 token bf16 占用更大。（影响一半读码一半推断：槽数与命中率是实测/读码，"若 FT 同条件"未测）

**证据位置**：
- FT：`python/freetoken/engine/engine.py:42-46,603-628`；`python/freetoken/engine/cache_budget.py:17-28,48-95,98-133`；`python/freetoken/engine/config.py:42-45`；`python/freetoken/kvcache/dsv4_paged_pool.py:11,164`；`_src_snapshot/retry2/.../hybrid_service.py:154-164`。
- Strata：`src/program/generate.cpp:4340-4347,4469-4492,4553-4579`；`src/core/layer.cpp:178-181,634-648,752-756,799-815`；`src/core/session.cpp:54-73`；`docs/DETAILS.md:78-94`；`_src_snapshot/strata_s1/stderr.log:15`。

## Q9 两路或批量（B=2）时 CPU 端是否合并同专家计算？

**FreeToken**（读码确认）：**不合并**。pass1 tile 索引含 (token, route k)，两个 token 命中同一专家会各自把该专家权重流一遍；代码注释把"expert dedup for bs>1"明列 deferred（理由：decode batch ≤4 很小）。两路共享的只是每次任务的固定开销（一次唤醒 + 两次屏障覆盖整个 batch），D08 复核："两路共享这份开销，诊断模式下两路步长只比单路长 13%"。

**Strata**（读码确认）：**合并**。窗口内按 distinct 专家分组成 `ExpertJobMulti`（聚合 nt 个 token 的 act/out 指针），一次 `run_split_multi_native`；**每个专家的权重只从 DRAM 流一遍**，NT 个 token 的循环在码表解码之后、同一权重块被窗口内所有 token 共享（docs/BATCHING.md:3-6 佐证）。

**差异对速度的可能影响**：B=1 无差异；B=2 / spec 窗口（S1 `--spec 2`）下 Strata 的 CPU 侧 DRAM 流量近半于 FT（对 miss 交集专家），且微基准显示 Strata 2-token 每专家只比 1-token 贵 26%（engine 0.658→0.828 ms），而 FT 第二个 token 是同专家全量重流（推断其边际≈另一个完整专家读取）。两路场景（window02 +55% 的主战场）差异被线性放大。

**证据位置**：
- FT：`cpu_moe_ext.cpp:1591-1597`（tile 索引）、`:1100-1101`（dedup deferred）；D08 文档顶部批注。
- Strata：`src/core/expert_source.cpp:3324-3345,3349-3351`；`src/kernels/cpu/iq_avx512.cpp:175-179`；`src/kernels/cpu/pool.cpp:627-660`；`docs/BATCHING.md:3-6`；微基准 nt=1 vs 2（MICROBENCH.md）。

## Q10 数值一致性

**FreeToken**（读码确认）：hybrid 与 offload 不逐位一致，来源四处：①块尺度施加顺序——GPU Triton 把 lut*scale 逐元素乘进权重再求和，CPU 在 16 元素块内先裸点积再乘块尺度（fp32 舍入序不同）；②激活量化——CPU VNNI 路径把激活量成 int8/per-16（真实量化误差），GPU 用 bf16 激活；③激活前舍入点——GPU 先把 GEMM 结果写 bf16 再过激活，CPU 在 fp32 上直接做激活再一次写 bf16；④top_k 归约——纯 offload 由 moe_sum_reduce fp32 累加一次写 bf16，hybrid 的 CPU 部分和先 bf16 落 pinned、H2D 后再与 GPU 部分和 bf16 相加（多一次舍入+一次 bf16 加法）。逐位一致从来不是验收标准（D08 的 G3 门是生成文本级逐字相同）。

**Strata**（读码确认）：`STRATA_IQ_MT_MIN` 读于 native_expert.cpp:111-112，默认 2——lone token 走 ggml vec_dot（与多 token 核舍入不同 → 贪婪输出可能随窗口草稿数变化）；=1 时 lone token 也走多 token 核，输出与草稿数无关（代价：IQ3_S AVX-512 decode −1..−3%，注释实测）。多线程归约确定：行区间静态等分、每行从头算到尾，每 token 累加器顺序与单 token 相同。精确复现三件套（docs/BATCHING.md:95-112）：`STRATA_IQ_MT_MIN=1` + `--pcie-frac 0` + `--adapt-every 1000000`。S1 满足后两条，未设 `STRATA_IQ_MT_MIN`（进程环境快照不可得——严格说 S1 输出仍可能随草稿数变化）。

**差异对速度的可能影响**：Strata 把"确定性"做成显式可关的开关（默认换速度）；FT 的差异是路径固有、无开关。对速度本身无直接影响，但 Strata 的做法让"复现问题"可定位、可对拍（影响：工程效率，推断）。

**证据位置**：
- FT：`cpu_moe_ext.cpp:14-16,287,1459-1477,1632-1634,1676`；`python/freetoken/kernel/triton/nvfp4_fused_moe.py:114-132`；`python/freetoken/moe/fused_nvfp4.py:188-194`；`python/freetoken/kernel/triton/fused_moe.py:142-153`；`python/freetoken/layers/moe.py:383`；`plan/02_开发任务/D08_hybrid执行器诊断埋点.md:36,77`。
- Strata：`src/kernels/cpu/native_expert.cpp:106-123`；`src/kernels/cpu/pool.cpp:664-683`；`src/kernels/cpu/expert.cpp:273-274`；`src/kernels/cpu/expert_layout.cpp:296-301`（oracle 开关）；`docs/BATCHING.md:95-112`。

---

## 排序：Strata 这条路径为什么更快（"每专家快 3 倍"说法的修正版）

按补充 1 的一步耗时模型 `t_step ≈ S_GPU + Σ层 max(G + f·t_P, O_C + (n−f)·t_C)`，结合本次读码与微基准，排序如下（1=影响最大）：

1. **每层固定开销 O_C 的结构**（依据：读码确认 + FT 微基准 + D08 实测）。FT 每层：协调轮询→提交前**单线程**激活预处理→CV 唤醒→2 次自旋屏障→CV 完工通知（纯池内往返下限实测 0.075 ms@24 线程；engine 内 O_C 0.19–0.26 ms，retry2 标定）；Strata：epoch 自旋（窗口内零睡眠）+ 无屏障静态行切分 + host 亲自算 + 图内等旗。48 层 × O_C 是每步固定差。
2. **B≥2/spec 窗口的批组织**（依据：读码确认 + Strata 微基准 nt=1/2）。Strata 每专家每窗只流一遍、token 共享；FT 按 (token,route) 重流。B=1 无差、两路时差近一倍 CPU 流量——这是 window02 两路 +55% 背后的重要结构差。
3. **每字节单核 kernel 效率**（依据：微基准）。FT NVFP4-W4A8 0.373 ms/MB vs Strata IQ3_S 0.253（kernels）/0.296（engine）ms/MB，差 25–32%（IQ 整数主干每 256 值一次 fp32 vs FT 每 16 元素一次块尺度+提交前量化）。
4. **格式字节数**（依据：读码确认 + 微基准）。NVFP4 2.77 MB/专家 vs Strata 混合 IQ 1.9–2.2 MB，少 21–31%。
5. **GPU 侧等待/拷贝节点开销**（依据：读码确认；量级推断）。FT 每层 4 个 memcpy 节点 + 2 memop；Strata 图内自旋核 + mapped 直读。FT 的 memop 不占 SM 设计本身更省 GPU，此项差异小。

**"每专家边际代价 t_C 差 3 倍"不成立**（依据：微基准 + 算法研究拟合）：FT 24 线程实测 t_C≈0.072 ms/专家，与 Strata 拟合区间 0.036–0.071 ms/专家（拟合不稳）重叠；差距主因是 O_C（每层固定开销）与 S_GPU（GPU 串行部分），不是每专家带宽。
