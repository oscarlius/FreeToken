# PORTABLE_IDEAS — 可移植到 FreeToken 的做法清单

- 调研日期：2026-10-11。目标树：FreeToken 发布版 481d3a7（`python/freetoken/` 前缀）；来源：Strata v0.1.41。
- 每项含：改动文件 / 估计人日 / 风险（默认路径影响、能否默认关闭）/ 预期收益与依据（读码、微基准或推断）/ 模型相关性（GLM-5.3 单专家约 14.2 MB ≈ Qwen3.8 的 5.1 倍时是否同样有效）。
- 收益参照系（实测/标定）：FT 每层固定开销 O_C ≈ 0.19–0.26 ms（retry2 标定，推断）；纯池内派发往返下限 0.075 ms（24 线程空任务，微基准）；每专家边际 t_C ≈ 0.072 ms（24 线程斜率，微基准）；48 层模型 → O_C 每省 0.1 ms ≈ 每步省 4.8 ms。

## P1（指定首项）自旋线程池：epoch 自旋 + 超时退睡眠 + host 参与计算

**做法**：把 worker 的空闲等待从"每层 1 次条件变量睡眠/唤醒"（`cpu_moe_ext.cpp:1874-1876`）改为 Strata `pool.cpp:496-523` 的 epoch 协议——worker 在任务代数 `epoch_` 上 `_mm_pause` 自旋，每 1024 次 pause 看一次时钟，超过自旋窗口才 mutex+CV 睡眠；publish 只 `epoch_++`（有睡眠者才 notify_all）。同时把两处相位屏障保持自旋但纳入同一 epoch 计数，并让提交/协调线程像 Strata 的 host 一样经同一计数器抢 tile 干活（`pool.cpp:539-548,693,823-833`），不再只睡觉等完工（现状 `cpu_moe_ext.cpp:1964-1968`）。

**改哪些文件**：
- `python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp`：`worker_loop`（:1869-1890）、`barrier`（:1568-1580）、`submit`（:1892-1962）、`sync`（:1964-1968）、协调线程循环（:2019-2085）；新增 `spin_before_sleep` 参数。
- `python/freetoken/moe/cpu_executor.py`：线程数/绑核解析（:119-141）加 env `FREETOKEN_CPU_MOE_SPIN_US`（默认建议 500 µs，=0 即现状）；协调核独占逻辑（:221-228）相应调整。

**估计人日**：5–8（含 D08 式埋点回归与 G3 文本等价门）。

**风险**：中。触碰同步核心；env gate 默认关闭即可完全不影响默认 offload 路径（CPU 池只在 cpu/hybrid 策略下启动）。
**CPU 占用影响（必须说明）**：自旋期间 24 个 worker 核近 100% 占用——现状的自旋屏障段本来也在烧这些核，自旋池把占用扩展到层间间隙，decode 期间整机 CPU 占用与功耗上升；与 481 生产服务同机时须靠绑核隔离（retry2 已用 `taskset -c 1,3-23,25,27-47` 划定，监控等旁路进程另加 nice/cgroup）。
**空闲退避（必须说明）**：decode 中相邻两层间隔 < 100 µs（推断：48 层 × 每层 GPU 工作 ≈ 30 ms/步 ÷ 48），自旋窗口 500 µs 覆盖整个 decode；无请求时最后一次任务后 500 µs 全体回 CV 睡眠、零占用——与协调线程已有的 50 ms 热窗退避（`cpu_moe_ext.cpp:2019-2085`）同一模式，Strata 亦同构（`pool.cpp:496-523`）。

**预期收益**：消掉每层 1 次 CV 唤醒/睡眠往返与完工通知链，O_C 向池内往返下限 0.075 ms 收敛（现为 0.19–0.26 ms）；推断每层省 0.05–0.15 ms，48 层 ≈ 每步 2.4–7.2 ms（单路 ~30 tok/s 即 33 ms/步，占比显著）。依据：读码 + FT 微基准（空任务往返）+ D08 实测 + Strata 对照。
**模型相关性**：与模型无关；GLM-5.3 专家更大时 O_C 占比变小，但绝对节省不变。

## P2 提交前的单线程激活预处理移出关键路径

**做法**：`submit()` 目前在协调线程上**单线程**做每 token 的 deinterleave + per-16 int8 量化（`cpu_moe_ext.cpp:1911-1941`）再 `notify_all`。两个可选方案：
- A：把输入预处理做成 phase-0 tile 分发给 worker（g 行预处理已有 worker 分摊先例：`:1799-1813,1854-1860`）；
- B：挪到 GPU 上做（ds_fp4 的 gpu_prequant 先例，`cpu_executor.py:303-316`：数值逐位相同、bs=1 实测 12.85→15.65 tok/s）。

**改哪些文件**：`cpu_moe_ext.cpp`（submit/run_task_body/pass 结构），方案 B 另改 `cpu_executor.py`（decode_submit 前加预处理 kernel 调用 + `set_input_prequant`）。
**估计人日**：2–3（A）/ 3–4（B，需一个预处理 CUDA kernel）。
**风险**：低-中；数值顺序需保持（A 内部分摊改变累加顺序风险小——预处理是逐元素独立操作）；env gate 默认关闭，默认路径不受影响。
**预期收益**：O_C 中单线程段实测量级：1 线程空任务 0.126 ms vs 24 线程 0.075 ms（微基准），差约 0.05 ms 含单线程预处理；挪走后每层约省 0.03–0.05 ms（推断），48 层 ≈ 1.4–2.4 ms/步。依据：读码 + FT 微基准。
**模型相关性**：与模型无关；H 越大预处理越贵，GLM-5.3（H 更大）收益更大（推断）。

## P3 按专家去重 + 多 token 共享权重流（B≥2 / spec 窗口）

**做法**：Strata 窗口内按 distinct 专家分组（`expert_source.cpp:3324-3345`）、每专家权重只流一遍、NT 个 token 循环在码表解码之后（`iq_avx512.cpp:175-179`）。FT 目前 pass1/pass2 tile 按 (token,route,32 行) 切（`cpu_moe_ext.cpp:1582-1678`），同专家被两路重复流（去重注释明列 deferred：`:1100-1101`）。改造：任务构建期对 batch 内 route 去重 → pass1 每专家只流一次权重、对多 token 累加（tile 改为 (distinct 专家, 32 行)，内层 token 循环）。
**改哪些文件**：`cpu_moe_ext.cpp`（`do_pass1` :1582-1637、`do_pass2` :1639-1678、tile 计数 `p1_total/p2_total` :1900 附近、run_task_body :1843-1867）；ids/w 布局不变。
**估计人日**：4–6。
**风险**：中——内核主循环重写，需数值回归（累加顺序变化 → 不逐位，需 G3 文本等价门）；env gate 默认关闭（如 `FREETOKEN_CPU_MOE_DEDUP=0/1`），单路行为不变。
**预期收益**：B=2 时 miss 交集专家的 DRAM 流量减半；Strata 实测 2-token 每专家只比 1-token 贵 26%（微基准 iq3_s/iq4_nl engine：0.658→0.828 ms），而 FT 现状第二个 token 是全量重流。两路 decode 的 CPU 侧时间近减半（推断，限于 miss 有交集的部分）。依据：读码 + Strata 微基准。
**模型相关性**：模型无关，但专家越大收益越大——GLM-5.3 每专家 14.2 MB（5.1 倍），DRAM 流量主导 CPU 侧时间，去重收益同比放大（推断）。

## P4 NUMA 内建选项（membind/interleave + 跨节点 K 维切分）

**做法**：FT 无内建 NUMA 感知（deferred 注释 `cpu_moe_ext.cpp:1102-1103`："Multi-socket would split each expert's K dimension per node"），现状靠外部 `numactl --interleave=all`（retry2 启动器）；Strata 同样靠外部 numactl（S1 argv），**可移植的不是 Strata 代码而是它验证过的组合**：内建 interleave 选项（启动时自包一层或 set_mempolicy）+ 可选的双节点 K 维切分（每个 socket 的 worker 只读本节点那半 K 维，节点间归约）。
**改哪些文件**：`moe/host_banks.py`（bank 分配加 membind 选项）、`moe/offload_cache.py`（:596-601 分配处）、`cpu_moe_ext.cpp`（点积 K 切分与跨节点归约，改动最大）。
**估计人日**：3–5。
**风险**：中；默认关闭（保持交错现状）；仅双路机器有意义；K 维切分改变归约顺序（不逐位，需等价门）。
**预期收益**：外部 interleave 已拿到大部分（两节点带宽聚合），内建 K 切分再把"每 worker 全读远端一半"变成"读本节点"，推断 CPU 侧有效带宽 +10–20%。依据：读码 + 推断（未实测）。
**模型相关性**：模型无关；GLM-5.3 大专家使 DRAM 带宽更紧，收益更重要（推断）。

## P5 不建议移植（记录结论与理由）

- **GPU 图内自旋等旗核**（Strata `wait_flag_ge`，verify_kernels.cu:970,1151-1198）：FT 的 `cuStreamWaitValue64` 不占 SM、功能等价且更省 GPU（`cpu_moe_ext.cpp:659-664`；`cpu_executor.py:32-50` 的设计注释）。不移植。
- **RouterLookahead 路由预读**（`verify.cpp:1990-1994`、`generate.cpp:4959-4991`）：服务于 PCIe 预取/Foresight 换槽；S1（--pcie-frac 0）未用，FT 的取数决策已 device-side 在 GPU kernel 内完成（`offload_kernels.py:291-410`），预读对 FT 结构收益低。不移植（低优先级）。
- **q8_K 激活量化**（Strata 侧）：FT 的 per-16 int8 粒度更细、精度更好；差异主要在实现位置（P2 已覆盖）。不移植格式本身。

## 汇总

| 项 | 人日 | 风险 | 默认路径 | 预期收益（依据） | GLM-5.3 适用 |
|---|---|---|---|---|---|
| P1 自旋线程池 | 5–8 | 中，env 默认关 | 不影响 | 每层 O_C 省 0.05–0.15 ms（读码+微基准+推断） | 同样有效 |
| P2 预处理移出关键路径 | 2–4 | 低-中，env 默认关 | 不影响 | 每层省 0.03–0.05 ms（读码+微基准） | 更有效（H 更大） |
| P3 专家去重+多 token 共享 | 4–6 | 中，env 默认关 | 不影响 | 两路 CPU 流量近减半（读码+微基准） | 收益放大（专家 5.1×） |
| P4 NUMA 内建 | 3–5 | 中，默认关 | 不影响 | CPU 带宽 +10–20%（推断） | 更重要 |
| P5 不移植项 | — | — | — | — | — |
