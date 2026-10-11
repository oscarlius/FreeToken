# KIMI 指令：hybrid 代码深度调研——FreeToken 与 Strata 在"CPU 计算未命中专家"上的实现差异（2026-10-11，主会话）

## 0. 背景与目标

**用户裁定**：把 hybrid 做好，作为 FreeToken 的主线。理由是换模型后同样受益。

**已知事实**（主会话已核实，见论文 v5.5 §7.7、§8.4）：

| 项 | FreeToken | Strata v0.1.41 |
|---|---|---|
| 同输入单路解码（32K 合成文本，不开 MTP） | offload 35.4 tok/s | 约 62 tok/s |
| hybrid 同窗口对照 | 单路 33.83 对 offload 30.17（+12%）；两路每路 25.4 对 17.0（+49%） | — |
| 每让 CPU 算一个未命中专家的代价（推算） | 约 0.20–0.24 ms（NVFP4，2.77 MB） | 约 0.071 ms（IQ3_S，2.04 MB） |

按主会话推算，两者差约 3 倍，这是差距的第二大来源。

**你的任务：只调查代码。** 把两边"CPU 计算未命中专家"这条路径逐层对照清楚，找出 Strata 快在哪里，以及哪些做法可以移植到 FreeToken。算法与成本模型由主会话另派的 Agent 负责，你不需要做。

**开始时间**：主指令（KIMI_EVENING_WINDOW_20261011）的 E6 报告写完之后。

## 1. 红线

- 两边代码都**只读**：不改、不提交、不重新构建，也不在原目录里生成文件。
- 不占 GPU，不起停任何服务，不碰 481。
- 不推送，不启动 Ollama，不改论文。
- 你的全部产出放在 `freetoken/development/hybrid_code_research_20261011/`（服务器同名目录：`/data2/FreeToken/development/hybrid_code_research_20261011/`）。
- 第 4 节的 CPU 微基准是**可选项**，要遵守那一节的时间限制；除此之外不做任何计时。
- 引用代码时一律写 `文件:行号`，并注明是哪棵代码树、哪个提交。读码得出的推断，标"推断"。

## 2. 代码位置

**FreeToken（发布版 481d3a7）**：服务器 `/data2/FreeToken/wt/release-e2/python/freetoken/`

| 文件 | 内容 |
|---|---|
| `moe/offload_cache.py` | 约 146–217 行：decode_target、hybrid_max_fetch、hybrid_fetch_fraction；`set_cpu_executor`；hybrid 的统计 |
| `layers/moe.py` | 328 行起：`_decode_hybrid` |
| `kernel/csrc/cpu_moe/cpu_moe_ext.cpp` | CPU 专家内核与线程 |
| `moe/bench_profile.py`、`moe/benchbw.py` | 自动取取数比例（`load_hybrid_fetch_fraction`） |
| `engine/engine.py` | 约 737–776 行：取数上限的设置 |

**FreeToken 的 D08 移植记录**：`plan/02_开发任务/D08_hybrid执行器诊断埋点.md`、`D08_C1_交付记录_20261005.md`；retry2 的启动参数见 `development/d08_d10_gpu_retry2_20261011/`。

**Strata（实测用的 v0.1.41，提交 fb58e0d）**：服务器 `/data2/Strata/wt/r002-v0141/`。本地 `strata/Strata` 是 v0.1.40，只作对照，以服务器上的 v0.1.41 为准。

| 文件 | 内容 |
|---|---|
| `src/kernels/cpu/` | `expert.cpp`、`expert_layout.cpp`、`iq_avx512.cpp`、`iq_avx2.cpp`、`native_expert.cpp`、`pool.cpp`、`pool_affinity_linux.hpp` |
| `src/core/expert_cache.cpp`、`expert_source.cpp` | 搜 `pcie_frac` |
| `src/core/layer.cpp`、`session.cpp`、`graph.cpp` | 每层的 CPU / GPU 分工与同步 |
| `third_party/ggml` | IQ 量化格式与点积 |
| `docs/HOW_IT_WORKS.md`、`DETAILS.md`、`BATCHING.md`、`DISJOINT_EXPERT_CACHE.md` | 设计说明 |

**实测运行参数**：`/data2/Strata/r002-prep/night_execution_20261009/raw-runs/v3-S1/`（`argv.json`、`config.json`、`stderr.log`）。

## 3. 必须回答的 10 个问题

每个问题都写成"FreeToken 怎么做 / Strata 怎么做 / 差异对速度的可能影响 / 证据位置"四栏。

| # | 问题 | 要点 |
|---|---|---|
| Q1 | 每层每步，一个专家在 GPU 算还是 CPU 算，由谁决定？ | FreeToken：命中与 PCIe 取数上限、取数比例。Strata：缓存命中、`--pcie-frac`、静态画像与自适应置换。写出决策发生在哪个函数、在 GPU 还是 CPU 上决定 |
| Q2 | CPU 读到内存里的专家是什么格式？ | 每个专家的字节数；是否需要反量化；FreeToken 的 NVFP4 在 CPU 上怎么算（逐块转 fp32？查表？），Strata 的 IQ3_S 怎么算 |
| Q3 | 激活值怎么处理？ | 是否先量化成 int8 / q8_K 再做整数点积；用到哪些指令集（AVX-512、VNNI、AVX2）。本机是 Xeon Silver 4310 双路，Ice Lake，支持 AVX-512 与 VNNI，不支持 AMX |
| Q4 | 线程模型 | 线程池结构；唤醒方式（自旋、休眠、屏障）；任务按专家切还是按行切；每层固定开销有多大；绑核与 NUMA 策略。FreeToken 的 D08 已移植了 Strata 的哪些部分、还缺哪些 |
| Q5 | 内存布局与 NUMA | 专家权重放在哪个 NUMA 节点（交错还是本地）；是否锁页；是否为 CPU 单独准备一份布局 |
| Q6 | CPU 与 GPU 怎么并行、怎么合并？ | 第 l 层的 CPU 计算与 GPU 计算是否同时进行；隐藏状态每层在 CPU 与 GPU 间怎么拷贝（D2H / H2D，同步还是异步）；用 event / stream 还是轮询；在哪一步合并部分和。Strata 的"路由预读"（提前算下一层路由、预取页面）是否用在 GPU 常驻的情形 |
| Q7 | 与 CUDA Graph 的关系 | FreeToken 解码是整步一张 CUDA Graph，hybrid 是否打断了图（走 eager？每层一次同步？）；Strata 怎么做。这一项可能是固定开销的大头 |
| Q8 | 缓存容量与显存预算 | FreeToken 2,700 槽对 Strata 9,196 槽。Strata 怎么把显存让给专家（KV int8、常驻 32K、流式 KV、`--expert-cache auto` 的算法），每一项省出多少显存 |
| Q9 | 两路或批量时的 CPU 路径 | B = 2 时，CPU 端是否合并两路对同一专家的计算，还是分开算 |
| Q10 | 数值一致性 | Strata 的 `STRATA_IQ_MT_MIN` 等可复现开关是怎么做的；FreeToken hybrid 与 offload 为什么不逐位一致，在哪一步引入舍入差异 |

## 4. 可选：CPU 微基准（核实"每专家 0.071 对 0.20 ms"）

**允许的时间**（同时满足）：

- 晚间主指令的 E6 已写完，481 已恢复；
- 不在 17:45 到 Codex 写出"D11-P0 测量完成"之间（若 20:00 前仍没写出，就以 20:00 为界）。这段时间 Codex 要在生产服务上测停顿，CPU 必须安静。

**限制**：

- 总时长 ≤ 15 分钟，最多用 24 个线程；
- 只用两边**已构建好**的二进制，或者 Python 扩展的现成入口；不重新编译 Strata；
- 找不到现成入口就不做，在报告里写明原因。

**测什么**：在同一组线程数（1 / 12 / 24）下，分别测：

- 单个专家的 GEMV（输入为 1 个 token）；
- 每层 3 个专家的批（对应失误率约 30%）。

两边各用自己的格式（NVFP4 对 IQ3_S），并且尽量各测一次对方的字节量，以便把"格式"和"实现"分开。每个点重复 5 次，报中位数和最小值，同时记录绑核与 NUMA 设置。

## 5. 产出

目录：`development/hybrid_code_research_20261011/`

1. `CODE_MAP.md`：两边 hybrid 路径的调用链图，从路由到专家计算、合并、写回，每一步写 `文件:行号`。
2. `Q1_Q10_COMPARISON.md`：按第 3 节逐题回答，并给出你对"每专家快 3 倍"原因的排序。逐条标"读码确认"或"推断"。
3. `PORTABLE_IDEAS.md`：可以移植到 FreeToken 的做法清单。每项写明：
   - 改哪些文件；
   - 估计人日；
   - 风险（是否影响默认路径、能否默认关闭）；
   - 预期收益，并注明依据（读码、微基准，或推断）。

   每一项还要说明它是否与具体模型有关。例如 GLM-5.3 的单专家约 14.2 MB，是 Qwen3.8 的约 5.1 倍，在这种模型上是否同样有效。
4. `MICROBENCH.md`（如做了第 4 节）：命令、原始输出、中位数表。
5. 协调日志写一行"hybrid 代码调研完成"，附 5 个文件的 SHA256。

## 6. 失败与停止

| 情况 | 处理 |
|---|---|
| 某个问题在代码里找不到答案 | 写"未找到"，并列出搜过的位置，不要猜 |
| 发现两边版本与上面写的不一致（提交号不对） | 停下，写明，等主会话 |
| 微基准需要重新编译或改代码才能跑 | 不做 |
| 任何操作要写进两边的代码树 | 不做 |

拿不准就停，在协调日志写原因。
