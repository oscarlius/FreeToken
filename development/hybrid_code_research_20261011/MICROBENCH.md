# MICROBENCH — CPU 微基准记录（2026-10-11）

## 合规与时间

- 允许条件核对：E6 完成于 13:34:00（COORDINATION_LOG），481 恢复于 13:31:10；本测量在 **13:45:53–14:03:13** 执行，早于 17:45 禁令起点；当时 Codex 尚未写出"D11-P0 测量完成"。
- 实际基准计时总量 ≈ 31 s（Strata 17.6 s + FreeToken 13.0 s），远低于 15 分钟上限。
- 线程上限遵守：最多 24 线程。两侧均 `nice -n 19`。**未触碰 GPU**：Strata 侧二进制为纯 CPU（源码无 cuda 调用，`src/kernels/cpu/iq_avx2_parity.cpp` 读码确认）；FT 侧 `CUDA_VISIBLE_DEVICES=""`，只调 `_cpu_moe.CpuMoeExecutor.create_task/run_task`（run_task 不碰 CUDA API，读码确认 `cpu_moe_ext.cpp:2096-2100` 附近 eager 路径）。
- 只用已构建二进制/现成扩展：Strata `build-r002-v0141/iq_avx2_parity`；FT `release-e2` 树内 `_cpu_moe.cpython-310-x86_64-linux-gnu.so`。无重新编译。

## 环境

- 机器：172.16.108.9，Xeon Silver 4310 双路（24 物理核 / 48 逻辑，Ice Lake，AVX-512+VNNI，无 AMX）。
- 起测时 load average 0.89；生产 481（`--moe-strategy offload`，taskset 1,3-47）在跑。
- NUMA/绑核：Strata 侧 `--cpu 4` 单线程绑核（进程未交错，单线程无 NUMA 维度）；FT 侧绑核 1T=[20]、12T=[6-17]（物理核）、24T=[4-23]+[28-31]（20 物理核 + 4 个 SMT 兄弟），bank 为 pageable 内存（非 pinned；对 CPU 读带宽影响小，推断）。FT ISA 实测选中 `avx512f+avx512vnni(nvfp4-w4a8)`。

## 1. FreeToken：池内空任务往返 + 1/3/10 专家批（t_C 斜率）

命令（脚本 `ft_cpu_bench.py`，同目录；合成 NVFP4 bank：E=512、H=2560、I=640、top_k=10、silu、weight_format=1，约 1.35 GB pageable）：

```
scp ft_cpu_bench.py 9:/tmp/ && ssh 9 'CUDA_VISIBLE_DEVICES="" nice -n 19 \
  /data2/FreeToken/venv/bin/python /tmp/ft_cpu_bench_20261011.py'
```

每点 5 个测量轮（空任务每轮 128 次、其余每轮 24 次、轮换专家窗口保证 DRAM 流式），表中为"5 轮中位数的中位数"与"全体最小步"。原始输出（含每轮中位数）：`microbench_raw_freetoken_cpu.txt`。

| 线程 | k=0 空任务 ms（min） | k=1 ms（min） | k=3 ms（min） | k=10 ms（min） |
|---|---|---|---|---|
| 1  | 0.1265 (0.1070) | 1.3156 (1.1670) | 3.7150 (3.2479) | 10.9444 (10.2451) |
| 12 | 0.0660 (0.0542) | 0.3197 (0.1564) | 0.7765 (0.3941) | 1.4624 (1.1698) |
| 24 | 0.0751 (0.0637) | 0.1432 (0.1343) | 0.2713 (0.2537) | 0.7741 (0.7262) |

推导：
- **O_C 池内下限**（空任务往返 = 唤醒 + 2 自旋屏障 + 预处理 + 完工通知）：1T 0.127 ms / 12T 0.066 ms / 24T 0.075 ms。1T 与 24T 之差 ≈ 提交侧单线程预处理被算进关键路径的体量（0.05 ms 量级）。
- **每专家边际 t_C**（k=3→k=10 斜率）：1T ≈ 1.033 ms、12T ≈ 0.098 ms、24T ≈ **0.072 ms**（与 retry2 标定的 0.04–0.07 ms 一致）。24T 下 t(k) ≈ 0.075 + 0.072·k 线性良好（k=10 预测 0.795 vs 实测 0.774）。
- 单线程每字节：1.033 ms / 2.77 MB ≈ **0.373 ms/MB**。
- 噪声说明：12T 的 k=1 行 5 轮中位数从 0.168 漂到 0.408（邻居负载），该点以 min=0.156 为参考；其余各行稳定（min 与中位数差 <10%）。

## 2. Strata：单线程每专家 DRAM 流式耗时（iq_avx2_parity --bench）

命令：

```
cd /data2/Strata/wt/r002-v0141/build-r002-v0141 && \
  nice -n 19 ./iq_avx2_parity --bench --dispatch --nt 1,2 --reps 5 --mb 256 --cpu 4
```

`--dispatch` 模式测三行：kernels（直调 SIMD 核）、ggml（ggml-cpu 逐 token 点积）、engine（池实际调用的 `native_gu_rows/native_down_rows`）。E ≈ 256 MB/每专家 个专家顺序流式（远超 L3，模拟 decode 的 DRAM 区间）。原始输出：`microbench_raw_strata_iq_avx2.txt`。每专家毫秒（5 轮中位数，括号内 min 从略，见原文）：

| pair（每专家字节） | nt=1 kernels | nt=1 engine | nt=2 kernels | nt=2 engine |
|---|---|---|---|---|
| iq3_s/iq4_nl（2.22 MB） | 0.561 | 0.658 | 0.887 | 0.828 |
| iq3_xxs/iq4_nl（2.08 MB） | 0.606 | 0.611 | 0.677 | 0.828 |
| iq2_s/q2_0（1.44 MB） | 0.439 | 0.491 | 0.542 | 0.622 |
| iq2_xxs/q2_0（1.25 MB） | 0.445 | 0.473 | 0.558 | 0.619 |

（nt=1 时 engine≈ggml 是预期：`native_gu_mt_min=2` 默认让 lone token 走 ggml vec_dot，见 Q10；nt=2 起 engine 走多 token 核，比 ggml 快 33–73%。）

推导：
- 单线程每字节：iq3_s/iq4_nl engine 0.658/2.22 ≈ **0.296 ms/MB**；kernels 0.561/2.22 ≈ **0.253 ms/MB**。
- 对照 FT 单线程 0.373 ms/MB → **Strata 每字节单核效率高 25–32%**。
- 注意：S1 实测模型是逐层混合量化（gate/up ∈ {Q3_K, IQ2_S}，down ∈ {IQ4_NL, Q2_0}，gguf 头读码确认），上表 4 个 pair 覆盖了实际混合的两端。
- 多 token：nt=1→2 每专家 +26%（engine 0.658→0.828）——第二个 token 几乎只付激活侧代价，印证 Q9 的"权重只流一遍"。

## 3. 偏差与未做项

- **Strata 池空任务派发延迟：未测**。候选入口 `pool_test`/`pool_stress`/`expert_multi_test`/`expert_parity` 在 CMake 有目标（CMakeLists.txt:1454-1480）但**未构建**（build 目录核实无此二进制）；规则禁止重新编译 → 按计划"找不到现成入口就不做"。`native_expert_bench` 是 GPU 布局对比（源码 `src/kernels/native_expert_bench.cpp:4-8,93-118` 读码确认用 cudaMalloc），勿误用。
- **Strata 的 1/3/10 专家批斜率：未按字面执行**。该二进制只支持单线程逐专家流式；每专家耗时本身就是边际代价（无池参与），故以 nt=1 的 engine 行充当 t_C 单核基线。
- **FT 侧与生产的差异**：bank 用 pageable 合成数据（生产为 pinned）；数值内容不影响耗时（e4m3 尺度固定 0x38=1.0 避免 denormal 减速，方法同 `benchbw.py:331-333`）；池内往返不含 D2H/H2D 与 memop 握手（那部分在 engine 内 O_C 0.19–0.26 ms 与池内下限 0.075 ms 之差里，推断约 0.12–0.19 ms 归传输+握手+协调轮询）。
- 两侧均未测对方字节量（计划建议项）：FT 内核只支持 NVFP4 等自身格式、Strata 二进制只支持 IQ 系 pair，互换需要改代码，属"需要重新编译才能跑"，按规则不做。

## 4. 结论（详见 Q1_Q10_COMPARISON.md 排序节）

1. FT 池内固定开销下限 0.075 ms@24T 远小于 engine 内 O_C 0.19–0.26 ms → 传输/握手/协调链约占 0.12–0.19 ms/层，是 O_C 的另一大成分（推断拆分）。
2. 每专家边际 t_C：FT 24T 0.072 ms ≈ Strata 拟合区间 0.036–0.071 ms → "每专家差 3 倍"不成立。
3. 单核每字节效率 FT 0.373 vs Strata 0.253–0.296 ms/MB，差 25–32%（格式+内核实现差）。
