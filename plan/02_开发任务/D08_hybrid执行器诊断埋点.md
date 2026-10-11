> 主会话（真实写入2026-10-11T00:29:48+08:00）：R048b S 臂诊断复核结果：每层 CPU 任务耗时 = 0.207 ms 固定开销 + 每个专家 0.084 ms。CPU 边际成本低于 PCIe，固定开销才是瓶颈；两路共享这份开销，诊断模式下两路步长只比单路长 13%。§7.7 的'固定延迟主导'假设由此得到数据支持。D08 两路测试按指令修订 v2 执行（只加预登记预测，单个配置点）。如果两路有收益，下一步是 D08 卡原计划第 2 项：移植 Strata 线程池（空闲时休眠、不自旋）。

> 主会话（真实写入2026-10-10T23:59:45+08:00）：D08 两路 hybrid 与 D10 η 微基准的 GPU 测试指令已归档到 [../D08_D10_GPU_TEST_DIRECTIVE_20261010.md](../D08_D10_GPU_TEST_DIRECTIVE_20261010.md)（SHA256 ef41f02dfc6d7057…）。用户已批准，尚未执行；执行前须完成该文件第五节的核对清单。

# D08 hybrid 执行器诊断埋点（每层服务时间分解）

> **2026-10-09 01:00 关闭决定**：按最新总负责人指令，以“已测量、无收益”关闭。T09 / E2-R048b 最快变体均值31.944579 tok/s，低于36.61 tok/s的跨配置offload参照；不追加移植或性能修复，代码保持默认关闭。本项转E3归档，不阻塞E2发布。原始轮次 `measured` 状态与证据不改；详见 `../01_测试与调研/results/T09-E2-R048b_20261008.md`。

> **10-06 21:05（PLAN §8.8）**：已 rebase 到 E2-base.1（4a12d7b）。T16 默认门轮次 **E2-R051-gate-D08**，GPU 队列第 5 位；之后 T09（E2-R048）。

> **2026-10-05 重新规划更新（优先于下文）**　详见 `../PLAN_20261005_重新规划.md`。
>
> **13:20 新增（PLAN §8.1）**：本卡属泳道 C1，**现在开始开发**，基于 E2-base `23f2e2c`，工作树 `/data2/FreeToken/wt/e2d08`。独占 `kernel/csrc/cpu_moe/`、`moe/cpu_executor.py`；改共享热点文件只加默认关闭的参数并登记。E2-base.1 打标签后 1 个工作日内 rebase；GPU 门按 PLAN §8.2 排队。

> 阶段 C，**P1**（原 P2）。范围扩大为「诊断 + 修复」，估计 4–7 人日（原诊断 2–3、修复 5–10）。基点改为 **E2-base.1**（卡D17），不再用 40fd5d4。旧D2（NUMA 分片）和旧D9（hybrid 动态分配）并入本卡。
>
> 1. **先诊断**：保留下文的 `FT_DEV_HYB_TRACE` 每层服务时间分解。
> 2. **再修复：移植 Strata 线程池**（MIT，保留版权声明）。参考：
>    - `_shared/Strata/src/kernels/cpu/pool.cpp`（779 行）：工作线程空闲时**休眠**（epoch 加状态字，`_mm_pause` 短暂等待后休眠），不做无限自旋。
>    - `pool_affinity_linux.hpp`：识别物理核与 SMT 兄弟核，可跳过首核；绑核失败时保留原亲和并报错。
>    - 替换 `kernel/csrc/cpu_moe/cpu_moe_ext.cpp` 中的自旋屏障（约 1568–1580、1850、1860 行）与 `moe/cpu_executor.py:92-141` 的绑核选择。
>    - 只移植线程池与亲和逻辑，**不引入 Strata 的 GGUF 内核**，NVFP4 数值路径不变。
> 3. **NUMA**：增加专家池 membind 到 node1 的选项（即 T09 的变体 C），默认关闭。
> 4. **验收**：T16 默认门（offload 路径不变）→ T09。判据见论文 §7.7：CPU 与 PCIe 同时运行时两路各自的完成率、每层服务时间分解、两路端到端速度。不以单独测得的 CPU 带宽作门。

>
> **本段取代下文中与之冲突的基点、优先级、估计、依赖与轮次号**（下文原表格保留作历史记录）。轮次号见 PLAN §5.3。

| 项 | 值 |
|---|---|
| 优先级 | P2（诊断支线，不进入核心验收） |
| 估计 | 2–3 人日（论文附录 D：诊断 2–3 人日；修复 5–10 人日不在本卡） |
| 基点 | `dev/d-series-clean` @ `40fd5d4`（与 E1-R002 同树，便于对照 4.84 tok/s） |
| 新分支 / worktree | `exp/e1r002b-hybtrace` / `/data2/FreeToken/wt/e1r002b` |
| 依赖 | 无 |
| 01 验证 | **T16**（`E1-R000b-gate-D08`，父树 40fd5d4；默认 offload 路径与 hybrid 路径在不设新开关时都要逐位——T16 跑默认 offload；hybrid 路径的不变性由本卡 G3 自检）→ **T09** |
| 论文依据 | v3.2 §9.1「判定：不能用单独测得的 CPU 带宽当充分门。要测三样东西：CPU 与 PCIe 同时运行时两路各自的完成率；每层的服务时间分解：CPU 计算、交接、屏障；两路端到端的解码速度」；机理假设（自旋屏障 + 抢占核） |

## 目标

在 `FT_DEV_HYB_TRACE=1` 时，记录每个解码步、每层 CPU 专家任务的时间分解，以及同一层 PCIe 缺失拷贝的起止，回答「多出的每层约 3.75 ms 花在哪里」（§9.1：hybrid 每 token 206 ms，offload 26.2 ms）。

## 范围

- 每层每步记录（写 `hyb_trace.jsonl`，路径同 `FT_DEV_D0_PATH` 前缀）：
  - 任务提交时刻（Python 侧）、协调线程收到时刻、各 worker 开始/结束、两次屏障（pass1 之后、prep 之后）的等待时长（每 worker）、D2H 输入拷贝与 H2D 结果拷贝的起止、该层 GPU 侧缺失拷贝（PCIe）起止；
  - 本层 CPU 专家数、GPU 搬运专家数（对应 §9.1「每层每步 CPU 算 2.43 个专家，经 PCIe 搬 0.62 个」）。
- 汇总脚本 `scripts/hyb_trace_summary.py <jsonl>`：每层中位数 / P90 的 CPU 计算、交接、屏障等待、被抢占迹象（屏障等待 > 1 ms 的次数与对应 worker 的绑核 CPU 号）；同层 CPU 与 PCIe 的重叠时间与各自完成率。
- `cpu_executor.py:319-320` 已打印 `pinned to cores a..b`；在 trace 头部再写一次每个 worker 的 CPU 号。

## 非目标

不改执行器的同步方式、不改绑核策略（那是修复，另立卡）；不做 w4a8 数值路径评估。

## 代码挂点（规划阶段在 e1r003 / d3512b4 上只读核实，40fd5d4 同源；路径相对 `python/freetoken/`）

| 位置 | 内容 |
|---|---|
| `moe/cpu_executor.py:91-116` `physical_core_cpus`；`119-141` `resolve_threads_and_affinity`（在 `sched_getaffinity` 内每物理核取一个逻辑 CPU）；`221-228` 自动模式把最后一个核留给协调线程；`319-320` 绑核日志；`92-141` 论文附录 D 引用段 | Python 侧任务提交与时间戳 |
| `kernel/csrc/cpu_moe/cpu_moe_ext.cpp:1527-1534` worker `pin_self`；`1568-1580` sense-reversal 自旋屏障（`_mm_pause`）；`1850`、`1860` pass1 后与 prep 后的屏障；`2006-2012` 协调线程绑核 | C++ 侧计时点（`rdtsc` 或 `steady_clock`，仅在开关开时） |
| `server/args.py:724-730` `--moe-cpu-threads`（只改线程数） | 参照 |
| `layers/moe.py:261-296` 解码缺失拷贝 | PCIe 侧起止 |

## 设计约束

- 环境变量 `FT_DEV_HYB_TRACE` 必须在 `moe/cpu_executor.py` 中读取（T09 用 `grep FT_DEV_HYB_TRACE <WT>/python/freetoken/moe/cpu_executor.py` 判断是否自动开启）。
- 默认关：C++ 计时代码用运行期标志判断，关时不调用计时函数；关时 offload 与 hybrid 两条路径都与父树逐位一致。
- 需要重新编译 `_cpu_moe*.so`：在新 worktree 内编译，**不得覆盖**其他 worktree 的 `.so`；交付记录写明编译命令与产物 md5。
- 计时开销：开发自检测一次开/关 hybrid 解码 tok/s 差（ABAB 各 2），写进交付记录。

## 验收门

| 门 | 条件 | 谁验证 |
|---|---|---|
| G1 | 单测通过；`hyb_trace_summary.py` 合成数据单测 | 02 |
| G2 | T16（offload 默认路径）通过 | 01 |
| G3 | 开发自检：hybrid、不设开关时 `cold_eq.py` 全文与 40fd5d4 hybrid 逐字相同 | 02 |
| G4 | 开发自检：开开关时每层记录完整（48 层 × 步数），屏障等待字段非空 | 02 |

## 需要的测试

`tests/moe/test_hyb_trace_guard.py`（开关关时不写文件、不调用计时）；`freetoken/scripts/tests/test_hyb_trace_summary.py`。

## 交付物

分支、重新编译的 `.so`（仅在本 worktree）、`scripts/hyb_trace_summary.py`、交付记录（T09 用的 `WT`、`EXP_COMMIT`）。

## 风险

中。C++ 改动与重新编译；计时本身可能扰动自旋屏障的时序（海森堡效应）——用开/关 tok/s 差评估，差 > 10% 时在交付记录中警示 T09 读数。

## 交付记录（02 执行者填写）

```
- 分支 / commit：
- worktree：
- 父树：/data2/FreeToken/wt/e1r000b / 40fd5d4
- 新增开关：FT_DEV_HYB_TRACE（env，默认关）
- 编译命令与 .so md5：
- 新增脚本：/data2/FreeToken/scripts/hyb_trace_summary.py
- 测试：
- 计时开销（ABAB）：
- 已知限制：
```
