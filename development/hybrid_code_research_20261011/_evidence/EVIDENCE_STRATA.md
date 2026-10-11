# EVIDENCE_STRATA — Strata 一侧"CPU 计算未命中专家"路径只读调研

- 调查方式：纯只读（Grep/Read），未 ssh、未执行任何 Strata 二进制。
- 代码快照根：`freetoken/development/hybrid_code_research_20261011/_src_snapshot/strata/`（tag v0.1.41；S1 实际构建目录为 `wt/r002-v0141/build-r002-v0141`，见 `strata_s1/config.json` 的 `exe`）。
- 行号引用约定：下文 `src/...`、`docs/...`、`CMakeLists.txt` 均相对上述快照根；S1 运行侧文件在快照根的兄弟目录，引用作 `strata_s1/...`（相对 `_src_snapshot/`）。
- S1 运行配置（`strata_s1/config.json`）：`--pack /data2/Strata-data/packs/iq3_s --native <IQ3_S GGUF shard1> --ple-gguf <shard2> --expert-profile expert-profile.bin --expert-cache auto --prefill auto --spec 2 --max-context 131072 --kv int8 --ple-io ram --kv-resident 32768 --adapt-every 100000 --prompt-cache 0 --adapt-swaps 0 --pcie-frac 0 --suffix-draft 0`。
- 外层包装（`strata_s1/argv.json:2-7`）：`numactl --interleave=all taskset -c 4-47`（NUMA 交织 + 绑 44 个逻辑核都在引擎之外完成）。
- S1 运行事实（`strata_s1/stderr.log`）：专家载入 RAM 46.84 GiB @0.54 GiB/s（:14）；GPU 专家缓存 9,196 个、17.45 GiB VRAM（:15）；decode ~60–67 tok/s、expert cache 命中率 ~62–66%（:25–80）。

## Q1 谁决定"这个未命中专家由 CPU 算"

决策点在 host 侧 `src/core/expert_source.cpp:3105` 的 `expert_pool_dispatch_multi`（S1 走 `--spec 2` 的 verify 窗口路径；单 token 版 `expert_pool_dispatch` 拒绝 native pack，`src/core/expert_source.cpp:2991-2997`）：

1. 窗口内 `n_tok*k` 个路由条目按路由序去重（`first_of`/`distinct`，`src/core/expert_source.cpp:3155-3164`），窗口上限 128 条（:3101-3102）。
2. 查驻留表 `host_res[layer*n_expert+e]`：slot≥0 → kind 0（GPU 缓存算，:3177-3182）；peer GPU 持有 → kind 2（:3183-3184）；Foresight 交换槽命中 → kind 0（:3187-3188）。
3. 其余为 miss，按路由序编号 `miss_rank`；最后 `m=(nmiss*pcie_num)>>8` 个且 pinned 可取的走 PCIe DMA（kind 1，:3166-3167、:3191-3199）；**剩下全部 kind -1 = CPU 池**。
4. S1 `--pcie-frac 0` → `pcie_num=0` → m=0，**所有未命中专家都归 CPU**（kind 默认 -1，:3175）。
- 驻留表来源：启动时按 `--expert-profile` 的顺序 `admit`+`fill_slot_blocking` 灌入 VRAM（`src/program/generate.cpp:4674-4688`，并回读校验一档 :4690-4698）；profile 文件读取在 `src/core/expert_cache.cpp:72-139`。
- 运行期置换 `adapt()` 在 `src/program/generate.cpp:11586-11678`（usage≥2 的未命中换入、层内最冷驻留换出、每轮 cap=adapt-swaps）；usage 计数仅当 adapt 启用才分配（`src/program/generate.cpp:11544` 附近；usage 累加在 `src/core/expert_source.cpp:3136-3138`）。**S1 `--adapt-swaps 0` → 置换实际不运行，驻留表在整个 run 内静止**。
- `pcie_num` 由 `--pcie-frac` 换算（`src/program/generate.cpp:7377`；probe 与默认值在 :2458-2470，native 默认约 0.55）。
- 关键时序：GPU 侧计划（命中组 + PCIe 份额）**先于** CPU 开工发布（注释 :3139-3140；fence+`P.publish`+`P.fetch` 在 :3235-3239），让 GPU 在 CPU 跑 miss 的同时先算 VRAM 命中组。

## Q2 IQ3_S 权重的存储与解码

- IQ3_S = ggml type 21，每 256 值一块 110 字节，布局 `d(fp16), qs[64], qh[8], signs[32], scales[4]`，块级 K=1.0（`src/kernels/cpu/iq_avx512.cpp:130-153` 的 `Fmt<21>`）。
- 值不反量化成 float：8-bit `qs` 拼 `qh` 的 1 bit 成 9-bit 索引查 `iq3s_grid` 码表得 4×int8（gather 版 :136-139，标量版 :141-146）；符号是 64-bit 掩码 `_cvtu64_mask64(u64(b+74+8j))`（:148），4 个 2-bit 子块 scale 解码于 :149-151。
- 每块再乘 `dx*dy`（fp16 权重块 scale × q8_K 激活块 scale）入 fp32 累加器（:181-183）。
- 每层每角色（gate/up/down）的具体 ggml 类型与 blob 内偏移来自 pack 里的 `native_experts.txt`，读取代码在 `src/kernels/cpu/expert_layout.cpp:370-476`；blob 布局 = gate 行 + up 行（`up_off`）+ down 行（`down_off=2*up_off`），由 `native_fmt` 计算（`src/kernels/cpu/native_expert.cpp:46-83`）。

## Q3 CPU kernel 的数据通路（整数点积，无反量化）

- 核心内循环 `row_dot`（`src/kernels/cpu/iq_avx512.cpp:155-186`）：激活是 ggml `block_q8_K`（int8）；权重码表值 g（int8）与符号处理后的激活做 `_mm512_maddubs_epi16(g, ys)` → `_mm512_madd_epi16(..., sc)` 全整数累加（:178）；符号通过 `_mm512_mask_sub_epi8` 按掩码取负（:177）；仅每 256 值块末尾一次 fp32 FMA（:181-183）。整行权重从 DRAM 流式读，带软件预取（:162-168）。
- 激活量化：优先 `q8k_quant_avx2`（`src/kernels/cpu/native_expert.cpp:90-104`），否则回退 ggml `from_float`。
- ISA 分发 `native_gu_rows`/`native_down_rows`（`src/kernels/cpu/native_expert.cpp:125-206`）：AVX-512（iq512，一次 4 块）→ AVX2（iq256）→ ggml `vec_dot` 兜底；多 token 核的起用阈值 `native_gu_mt_min`（:106-123，见 Q10）。
- 注意：s2 路径（`src/kernels/cpu/expert.cpp`，Q2_0 blob + `act_quant_q8_1` + VNNI `dpbusd`）是另一种 pack 的 CPU 路径，**不是 S1**；S1 native IQ3_S 包在 mode 5/6 下走 `native_gu_rows`/`native_down_rows`（`src/kernels/cpu/pool.cpp:650、660`），Q2_0 门控分支在 :635-646、:651-656。

## Q4 线程池模型与同步开销

- 池 = 每物理核一个 worker：sysfs 拓扑探测、剔除 SMT 兄弟（`src/kernels/cpu/pool.cpp:180-337`），host 自己占的第一个物理核让出（:305-308）；混合架构（P/E 核）默认 `p_cores-1`（:443-444）；pthread 绑核（:347-358 与 :459-463，`pool_affinity_linux.hpp:60-66`）。
- 唤醒：worker 在 `epoch_` 上 `_mm_pause` 自旋（:496-523，每 1024 次 pause 看一次时钟），超过 `spin_before_sleep_`（默认常量 `kSpinBeforeSleep` 在 pool.hpp，**快照缺该头文件，默认值未找到**；env `STRATA_POOL_SPIN_US` 覆盖，:439-440）后走 mutex+条件变量睡眠；host `publish()` = `epoch_++` 且 sleepers>0 时 `notify_all`（:476-487，注释给出防丢唤醒的 seq_cst 论证）。
- 无屏障库：host 自旋等待 `wait_parked`（:564-583）/`wait_done`（:585-606），均有 kStall 看门狗（卡死则 `release_gpu_waits`+abort，issue #29/#267）。
- **host 也干活**：host 经同一 `head_` 计数器 `claim` 抢任务（`claim` :539-548；`run()` 的 host 循环 :823-833，注释 :809-822 说明动机： pinned host 核不再空转）；`run_phase` 同样 `if (host_works_) drain(-1, ...)`（:693）。
- 任务切分（native multi）：每层两个 phase——5=所有专家的 gate/up 行、6=所有专家的 down 行（`run_split_multi_native`，:759-788）；phase 内把 `nb*FF`（或 `nb*H`）行空间按任务数静态等分 `g0=mrows_*i/mtasks_`（:630-633），一个任务可跨专家边界；任务数约 3×(worker+host)（`phase_tasks` :716-718）；专家多于 `kMaxSplitMulti` 时分批（:762-764）。两 phase 之间由 host 串行做 SwiGLU 后激活量化（:772-775）。
- 每层 = 2 次 `publish` + 每 phase `wait_parked → begin_batch → (host drain) → wait_done → wait_parked`（:688-698），自旋窗口内 worker 不睡眠。
- 计时拆分：池侧 `ms_wait_park_/ms_drain_/ms_repark_`（:844-846）、multi 三段 `ms_multi_gu/q/down`（:781-783）；dispatch 侧 `ms_plan/ms_actq/ms_jobs/ms_run`（`src/core/expert_source.cpp:3372-3376`）。

## Q5 NUMA / 大页 / 锁页

- 引擎代码内**没有** NUMA API、mbind、hugepage 调用（全快照 grep 无命中）；S1 的 NUMA 交织与绑核完全靠外层 `numactl --interleave=all taskset -c 4-47`（`strata_s1/argv.json:2-7`）。
- 锁页：RAM 侧 complement 区用 `cudaHostAlloc(Mapped|Portable)`，失败退 `malloc`+`mlock`（`src/core/expert_source.cpp:2407-2468`；`mlock` 在 `src/platform/memory.cpp:121-129`）；分步注册带 `STRATA_PIN_GUARD` 保护（:2474-2529）。Arena（含 y_miss mapped 行、门铃字）整体钉住并建 device alias（:4072-4086、:4154-4161）。

## Q6 CPU 计算与 CUDA Graph 的同步

- decode 用 CUDA Graph：整个 verify 窗口捕获为一张图（`src/core/verify.cpp:1676-1769`；token 级整图在 `src/core/session.cpp:836-908`）。CPU 路径在图外，经 mapped pinned 内存上的标志字同步。
- 门铃（GPU→CPU）：`moe_route` 末尾把 x/ids/weights 拷进 mapped 内存再 `doorbell_ring`（`src/core/layer.cpp:376-391`；`doorbell_publish`/`doorbell_ring`/`doorbell_wait` 定义在 `src/kernels/cuda/elementwise.cu:209-226、428-432`；序号取自 host 副本使 graph 重放幂等，注释 :385-390）。
- host 侧：自旋 volatile `h_seq_` 门铃（`src/core/verify.cpp:1971-1999`，带 20 s 超时与 `release_gpu_waits` 看护）→ 跑 CPU 池（:2008-2010）→ fence/sfence 后写 `*flag = want`（:2039；池未出计划时写空计划兜底 :2018-2027）。mapped 字对 GPU 自旋核可见的论证在 :276-278。
- GPU 图内：`wait_flag_ge`/`wait_flag_ge_or` 自旋核（`src/kernels/cuda/verify_kernels.cu:970、1151-1198`）依次等 m_flagA_（计划已发布，`src/core/verify.cpp:1449`）→ VRAM 命中组 `native_expert_grouped`（:1453；E-6 device_plan 分支 :1445-1447）→ m_flagB_（PCIe DMA 落地，:1456；`fetch_dma`+`cudaLaunchHostFunc` 在 :2168-2194）→ m_flag_（CPU 行就绪，:1473）→ `copy_rows_from_mapped`/`copy_from_mapped` 从 mapped pinned y_miss 读 CPU 行（:1477-1481）→ `moe_hit_add` 合并命中+未命中（:1483）→ `native_moe_combine_multi` 整窗一次 combine（:1495-1498）。

## Q7 与 GPU 命中路径的重叠手段

- 计划先行发布（`src/core/expert_source.cpp:3139-3140、3235-3239`）→ GPU 在 CPU 跑 miss 的同时先算 VRAM 命中组（`src/core/verify.cpp:1453`）。
- RouterLookahead：host 线程用本层 x 预计算下一层 router top-k（`src/core/verify.cpp:1990` 附近），跳过已驻留，`src_->warm` 暖页（:1994）；`STRATA_FS_SLOTS` 开启时（仅 dj==0）喂 ForesightSwap；接线在 `src/program/generate.cpp:4959-4991`（`STRATA_LOOKAHEAD=0` 关闭）。
- PCIe 份额用 copy engine 与 CPU 工作并行（`P.fetch` 注释 "the copy engine, beside the CPU's work"，`src/core/expert_source.cpp:3239`）；S1 因 `--pcie-frac 0` 无此项。

## Q8 专家缓存容量与 KV 驻留

- `--expert-cache auto`：`slots = (free_b − reserve − mtp − pipe − prefill) / max_blob`，再 `min(slots, profile.size())`（`src/program/generate.cpp:4340-4347`）；native+profile 分支按 profile 顺序逐层累积各层 blob（:4469-4492）；放不下时 ×3/4 重试（:4553-4579）。
- S1 实际 9,196 槽 = 该计算结果，运行日志佐证：`strata_s1/stderr.log:15`（9,196 experts、17.45 GiB VRAM）；精确算术入"未找到清单"。
- KV int8：k/v 以 int8+scale 存储（`src/core/layer.cpp:752-756`；开关 :178-181）；`kv_plan`（:634-648）按 `g_kv_resident`（:517、:665-666）决定 VRAM 驻留窗；流式时权威 KV 放 pinned+mapped host（:799-815）。
- 文档佐证：`docs/DETAILS.md:78-80`（64K+ 上下文只留 32K 窗在 VRAM，例：1589→3872 个专家进 VRAM）、:85-94（q4_0 KV 减半、k8v4 −23%）；`session_bytes` 在 `src/core/session.cpp:54-73`。

## Q9 多 token 合并（B≥2 时 CPU 侧如何组织）

- 窗口内按 distinct 专家分组：`job_of[e]` 映射，`ExpertJobMulti` 累积 nt 个 token 的 act/out 指针（`src/core/expert_source.cpp:3324-3345`），随后一次 `pool->run_split_multi_native`（:3349-3351）。
- 每个专家的权重只从 DRAM 流一遍：NT 个 token 的循环在码表解码之后（`src/kernels/cpu/iq_avx512.cpp:175-179`），同一权重块被窗口内所有 token 共享。
- 池内 phase 5/6 把"所有专家×行"空间静态等分给 worker（`src/kernels/cpu/pool.cpp:627-660`），所以 batch 越大每核分到的连续行区间越大。
- 文档：`docs/BATCHING.md:3-6`（共享专家每窗读一次）。

## Q10 确定性 / 复现开关

- `STRATA_IQ_MT_MIN`：读于 `src/kernels/cpu/native_expert.cpp:111-112`，默认 2（lone token 走 ggml vec_dot，与多 token 核的舍入不同 → 贪婪输出可能依赖窗口内草稿数）；=1 时 lone token 也走多 token 核，输出与草稿数无关，实测 IQ3_S(AVX-512) decode −1..−3%（注释 :106-110）。另有 `STRATA_IQ3S_MT1`（仅 AVX2-only CPU 的 IQ3_S opt-in，:113-122）。
- 多线程归约确定：行区间静态等分、每行从头算到尾（`src/kernels/cpu/pool.cpp:664-683` 及注释 :665）；每 token 累加器顺序与单 token 相同（`src/kernels/cpu/expert.cpp:273-274` 注释）。
- oracle 开关（`expert_oracle_q8_0_enabled`）在 `src/kernels/cpu/expert_layout.cpp:296-301`；命中时池退回单 token 路径（`src/kernels/cpu/pool.cpp:702、722`）。
- `docs/BATCHING.md:95-112` 给出精确复现三件套：`STRATA_IQ_MT_MIN=1`、`--pcie-frac 0`、`--adapt-every 1000000`。
- S1 符合后两条（`--pcie-frac 0`、`--adapt-every 100000` 且 `--adapt-swaps 0`），但 config/argv 未设 `STRATA_IQ_MT_MIN`（进程环境快照不可见）——S1 输出严格说仍可能随窗口草稿数变化。

## 调用链（S1 decode，一层 MoE 的 miss 路径端到端）

1. `src/core/layer.cpp:357-391` `moe_route`：router top-k → `doorbell_publish` + `doorbell_ring` 写 mapped `d_seq`（kernel 定义 `src/kernels/cuda/elementwise.cu:209-226、428-432`）。
2. `src/core/verify.cpp:1971-1999`：host 自旋 `*h_seq_ >= want`（图重放到本层即"响铃"）。
3. `src/core/verify.cpp:2008-2010` → pool 回调 = `src/program/generate.cpp:955-976` `drive_pool_multi`。
4. `src/core/expert_source.cpp:3105` `expert_pool_dispatch_multi`：去重/查 `host_res`（:3155-3182）→ S1 全部 miss 落 kind -1；usage 累加 :3136-3138。
5. :3139-3239：GPU 计划（命中组）先行 fence+publish（flagA）+ fetch（flagB，S1 空）。
6. :3324-3345 按 distinct 专家分组成 `ExpertJobMulti`；:3350 `pool->run_split_multi_native`。
7. `src/kernels/cpu/pool.cpp:759-788`：`run_phase(5)`（gate/up）→ host 量化（:772-775）→ `run_phase(6)`（down）。
8. `src/kernels/cpu/pool.cpp:688-698` `run_phase`：`wait_parked` → `begin_batch`（epoch+1，`publish` :476-487）→ host `drain`（:693）→ `wait_done` → `wait_parked`。
9. worker/host `drain`（:608-686）→ mode 5/6（:627-660）→ `native_gu_rows`/`native_down_rows`（`src/kernels/cpu/native_expert.cpp:125-206`）→ `iq_avx512.cpp:155-186` `row_dot` 整数点积；结果写 mapped `y_miss`。
10. host fence 后 `*flag = want`（`src/core/verify.cpp:2039`）。
11. GPU 图内：`wait_flag_ge(m_flag_)`（`src/core/verify.cpp:1473`）→ `copy_rows_from_mapped`（:1477-1481）→ `moe_hit_add`（:1483）→ `native_moe_combine_multi`（:1495-1498）。

## 微基准 / 验证程序入口

前提：`STRATA_BUILD_TESTS` 默认 OFF（`CMakeLists.txt:94-99`），且发布源码快照不含 `tests/` 与 `bench/micro/`；下列 CPU 目标只链 `strata_kernels_cpu`（无 GPU 依赖），构建后可直接跑。

CPU 路径直接相关（无需 GPU）：
- `iq_avx2_parity`（`CMakeLists.txt:1230-1237`）：AVX2 IQ kernel 1..8 token 互对 + 对 ggml-cpu 逐位校验；`--bench` = 单线程每专家毫秒、权重从 DRAM 流式读（注释 :1230-1231）。含 `STRATA_IQ3S_MT1=1` 变体测试（:1236）。
- `q8k_quant_parity`（`CMakeLists.txt:1238-1244`）：Q8_K 激活量化器对 ggml 逐字节；`--bench` 计时。
- `expert_multi_test`（`CMakeLists.txt:1454-1457`）：多 token vs 单 token 逐位（AVX-512，无则 SKIP 77）。
- `expert_parity`（`CMakeLists.txt:1467-1472`）：CPU 专家对真实 pack blob；ctest 用 `--selftest`。
- `pool_test`（:1474-1476，`--selftest`）、`pool_stress`（:1477-1480，`pool_stress 20`，小批+睡眠 worker 的挂起回归）、`pool_affinity_test`（:1436-1445，Linux 用 :1442）。
- `router_dot_parity`（:1219-1228）：lookahead 的 router dot 各 ISA 档对 double 参考。
- `src/kernels/native_expert_bench.cpp`（`CMakeLists.txt:1387-1389`）：**是 GPU 分组专家的布局对比**（modes = `STRATA_EXP_MODE`，`src/kernels/native_expert_bench.cpp:4-8`），只含 CPU 头文件用于 blob 几何，不是 CPU miss 路径的 bench——勿误用。

需 GPU 构建： `native_expert_parity`（`CMakeLists.txt:1383-1416`，GPU+CPU 专家对 float 参考，注释 :1392；`--synthetic` 无需模型）、`iq_parity`（:666-709，GPU 反量化对 gguf-py fixtures）、`hit_cpu_order_parity`（:1431-1434，源不在快照）。
ISA 编译开关：iq_avx512 用 `-mavx512f;bw;vl;dq;vnni;vbmi`（`CMakeLists.txt:1200`），iq_avx2 `-mavx2;-mfma;-mf16c`（:1201），`STRATA_NATIVE_EXPERTS=1`（:1212）。

## 未找到清单

1. `kSpinBeforeSleep` 的默认微秒值 —— 定义在 `pool.hpp`，快照 `src/kernels/cpu/` 仅有 `pool_affinity_{linux,win}.hpp`；只看到 env 覆盖逻辑（`src/kernels/cpu/pool.cpp:439-440`）。
2. `native_experts.txt` 的实际数值 —— 在 pack 产物（`/data2/Strata-data/packs/iq3_s`）内，快照只有读取代码（`src/kernels/cpu/expert_layout.cpp:370-476`）。
3. 9,196 槽的精确算术 —— 取决于启动瞬间 `free_b`；`strata_s1/stderr.log` 未见 `src/program/generate.cpp:4345-4347` 的 "expert cache auto" 明细行，只有结果行（`strata_s1/stderr.log:15`）。
4. `bench/micro/hit_cpu_order_parity.cu` 源码 —— `CMakeLists.txt:1431-1434` 以 EXISTS 守卫引用，发布快照无 `bench/micro/`。
5. `tests/` 目录全部内容（发布快照不含）。
6. `STRATA_POOL_SPIN_US`、`STRATA_IQ_MT_MIN` 在 S1 进程环境中的实际取值 —— 不在 `strata_s1/config.json`/`argv.json` 中，进程环境快照不可得。
7. S1 机器的物理核拓扑 —— 池 worker 数 = 物理核（去 SMT 兄弟）且 host 让出一核（`src/kernels/cpu/pool.cpp:180-337、305-308`）；`taskset -c 4-47` 是 44 个逻辑核，但运行时拓扑探测结果无法从快照推出。
