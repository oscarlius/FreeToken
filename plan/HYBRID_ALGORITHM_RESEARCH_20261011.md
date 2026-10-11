# hybrid 算法与成本模型研究（2026-10-11，算法研究员，只读）

本报告只读代码、论文与已有工件，没有改动代码或论文，没有占用 GPU，没有在服务器上计时、起停服务或推送。所有推算都用本地脚本完成，脚本放在会话 scratchpad，不进仓库。

标签说明：
- **实测**：附工件来源；
- **推算**：由实测参数加明示假设算出，附依据；
- **推断**：读代码得出、未经运行验证。

文中的代码位置：FreeToken 指服务器 `/data2/FreeToken/wt/release-e2/python/freetoken/`（发布版 481d3a7），Strata 指服务器 `/data2/Strata/wt/r002-v0141/`（v0.1.41，fb58e0d）。

> **午后补充（2026-10-11）**：用户告知早上的测试与 KIMI 的代码调研都已完成，新增数据整合在 **§6**，主要有三类：
> - window02 同窗口 A/B：单路 +21%，两路 +55%；
> - KIMI 的 CPU 微基准：线程池空任务往返 0.075 ms，每个专家边际 0.072 ms；
> - 协调日志里已有的 D08 诊断实测：每层 CPU 任务 0.207 ms 固定 + 0.084 ms/专家。
>
> 结论方向不变，但两处数字要修正：固定开销区间改为 0.11–0.25 ms/层；固定开销降到约 0.05 ms 后的推算改为单路 40–46、两路每路 28–31 tok/s。论文已出 v5.6，已采纳本报告的主要内容，剩余缺口见 §6.4。

---

## 0. 结论摘要

1. **单路解码里，CPU 算未命中专家只能与同一层 GPU 的 MoE 部分并行，不能与注意力等串行部分并行**（推断，读码；Strata 源码自述同一事实）。
   - FreeToken：每层在同一条流上依次执行"提交 CPU → 取数 → GPU 算命中 → 等 CPU → 相加"（`layers/moe.py:328-383`），下一层要等这一层的输出。
   - Strata 在 `include/strata/core/expert_cache.hpp:3-6` 写明："the CPU work is 96% exposed because the residual chain is strictly serial"。
   - 因此一步耗时应写成 $t=F'+\sum_l \max(\cdot)$，而不是 $\max(F,\ \text{CPU})$。主会话 §8.4 的两个结论都建立在后一种形式上，需要重算：
     - 每个 CPU 专家约 0.20–0.24 ms；
     - 换成 Strata 结构后单路可到 55–65 tok/s。

2. **按串行链模型，用 retry2 的单路 33.83 与两路 25.4 标定**（推算）：
   - FreeToken hybrid 每层有约 **0.19–0.26 ms 的固定开销**，折合每步 9–12.5 ms；
   - 每个 CPU 专家的边际代价约 **0.04–0.07 ms**，等效 40–70 GB/s。
   - 样本外检查：R048b S 臂（32K 合成文本，每层 CPU 算 2.43 个、PCIe 搬 0.62 个）推算 33.5 tok/s，实测 31.94，模型偏高约 5%。
   - 若每个 CPU 专家真要 0.20–0.24 ms，两路每路最多约 15–18 tok/s，而实测是 25.4。所以这个值可以排除。

3. **读码找到的固定开销来源**（推断）：
   - FreeToken 的 CPU 池每层都要：经 `condition_variable` 唤醒 21 个工作线程（`cpu_moe_ext.cpp:1876`、`:1961`），协调线程在 `sync_cv` 上睡眠后再被唤醒（`:1964-1968`），中间还有两次自旋屏障（`:1849-1860`）。
   - Strata 的工作线程在有流量时自旋停泊，只有空闲超时后才睡（`src/kernels/cpu/pool.cpp:491-535`）。
   - FreeToken 内核本身不慢：本机 benchbw 测得单独 47.62 GB/s，与 DMA 并发时 40.85 GB/s（实测，`~/.cache/freetoken/benchbw/GPU-052dcdb7-….json`，2026-09-29）。

4. **Strata 的 0.071 ms/专家不是稳健估计**：
   - 它是 3 点拟合。用同一 stderr 的 7 点拟合得 0.045 ms，32K 的 4 点拟合得 0.036 ms，斜率不稳（推算，`v3-S1/stderr.log:23-80`）。
   - S1 是 Strata 的可复现配置（`--pcie-frac 0 --adapt-every 100000 --adapt-swaps 0`，静态画像），不是它的默认配置（实测 argv，`strata/development/r002_v0141_night_execution_20261009/receipt/S1.json`）。默认配置是 `pcie_frac` 0.55 并按链路缩放、开启自适应置换（`src/program/generate.cpp:555,1556-1558,559-560,586`）。

5. **1.8 倍差距的重新分解**（推算）：
   - FreeToken hybrid 单路每步约 29.6 ms，约等于 GPU 串行部分 11.2 + 每层固定开销 9–12.5 + CPU 边际 6–9。
   - Strata S1 每步约 16 ms，约等于串行与固定部分 3–11 + CPU 边际 4–13。
   - 主要差距在固定部分：CPU 池的握手，以及 FreeToken 更大的 GPU 串行部分。不在每专家带宽，也不在量化。

6. **最优拆分**（推算）：
   - 闭式解为 $f^\*=\mathrm{clip}\big((O_C-G+n\,t_C)/(t_P+t_C),\,0,\,n\big)$。
   - 上游 [1] 的 $q^\star=m\,B_P/B_H$ 与 FreeToken 代码的 $r=B_P^{ov}/(B_P^{ov}+B_C^{ov})$（本机为 27.7%）都是 $O_C=G=0$ 时的特例。
   - 在现有固定开销下，规则每层少取约 0.7–1.4 个专家；改用最优拆分，单路 +6–12%，两路 +3–9%。
   - 把 $O_C$ 降到 ≤0.05 ms 以后，规则与最优几乎一致。届时单路约 **44–50**，两路每路约 **27–32** tok/s（推算）。

7. **benchbw 的"CPU 带宽 > 2 × PCIe 带宽"阈值是代码独有的规则，上游论文没有**：
   - 本机 profile 的比值为 1.962，判为 offload（实测 profile）；但实测 hybrid 单路 +12%、两路 +49%。
   - 按 [1] 自己的模型，只要 $B_H>B_P$ 就应选 hybrid。
   - 正确的判据是逐层比较 $O_C<G+n\,t_P$，再在步级比较期望耗时（§2.4）。

8. **GLM-5.3-Flash**（推算；GPU 串行部分取 20 ms，失误率取 55–85%）：

   | 项 | 单路 tok/s | 两路每路 tok/s |
   |---|---|---|
   | offload | 5.4–7.8 | 2.8–4.2 |
   | hybrid（固定开销小） | 10.5–14.3 | 5.9–8.4 |
   | 现有固定开销下 | 少 5–9% | — |
   | 主存读带宽上界 | 10.9–15.1 | — |

   - 瓶颈：offload 卡在 PCIe；hybrid 卡在 DMA 与 CPU 共用的主存读带宽。
   - GLM 单专家大，固定开销被摊薄，现有规则约等于最优，hybrid 相对 offload 约 1.8–2.0 倍，高于 Qwen3.8 现状的 1.12 倍。

9. **"把 hybrid 做好，换模型后同样受益"方向成立，但要把"做好"拆成两类**：
   - 能随模型迁移的：CPU 内核带宽、NUMA 放置、考虑竞争的拆分规则、主存上界；
   - 只对小专家模型显著的：每层固定开销。它恰好是 Qwen3.8 的主瓶颈。
   - 成立条件见 §3.3。

10. **论文 v5.5 的缺口**：
    - §2.1 对 [1] 的 $q^\star$ 引用是正确的，但缺 hybrid 的结构项（§4.3、§4.7），也缺 $\phi$ 与规则、实测的对接（§4.4）；
    - 没有区分以下几点：[1] 正文要求"至少保留 1 次取数"，代码的比例模式会取 0 个；代码使用并发实测带宽比（27.7%）和 2× 阈值，这两项是代码独有的；
    - §7.7 写"同一窗口内依次起 offload 与 hybrid"不准确：offload 单路 30.17 来自 retry1 window02，两路 offload 来自 10-10 夜的闭环 X 组，retry2 的 RESULT_REPORT 也明说是"historical reference comparisons"；
    - §8.4 的分解需要按串行链模型重写。

---

## 1. 算法对照

### 1.1 FreeToken hybrid（发布版 481d3a7）

```text
# 离线：ft bench bw → ~/.cache/freetoken/benchbw/<gpu-uuid>.json
#   每种格式记录 cpu_moe_gbs、pcie_gather_gbs（各自单独测），以及 cpu_moe_overlap_gbs、pcie_gather_overlap_gbs（两者并发测）
#   recommended = "hybrid" if cpu_gbs > 2.0 * pcie_gbs else "offload"           # benchbw.py:598-600
# 本机 nvfp4（几何 3072x1536，专家 7.97 MB）：47.62 / 24.27，并发 40.85 / 15.64，比值 1.962 → "offload"   # 实测 profile

启动:
  策略为 auto 且 profile 推荐 hybrid → hybrid，否则 offload                          # engine.py:1902-1946
  --moe-hybrid-max-fetch 默认 -1（自动）                                             # engine.py:1675
  r = pcie_ov / (pcie_ov + cpu_ov)；无并发数据时 r = pcie / cpu；无 profile 时固定上限 1   # bench_profile.py:156-191；engine.py:758-787
  # retry2：r = 27.7%，CPU 池 21 线程，绑核 1..22                                     # 实测 serve.log:20-22

每个解码步（整步一张 CUDA Graph）:
  for l in 0..47:
    x  = 注意力/GDN → 超连接 mix
    sh = shared_expert(x)                       # qwen4_exp/moe.py:22-24，在路由专家之前、不与 CPU 重叠
    ids, w = topk(router(x)); raw = ids.clone()
    # GPU 内核 _ensure_experts_hybrid_kernel（offload_kernels.py:291-410）
    A = unique(ids); M = {e ∈ A | slot[l,e] == -1}; n = |M|
    lo = floor(n*r);  f = argmin_{f∈{lo,lo+1}} max(f*(1-r), (n-f)*r)   # Q16 定点；n ≤ 2 时 f = 0
    F = M 中按 expert_recency 降序取前 f 个（并列取小 id）              # FREETOKEN_HYBRID_FETCH=recency
    对 F 中每个 e：在不属于本层活跃专家的槽里按 LRU 时间戳 argmin 选牺牲槽，写入映射
    ids ← 槽号（命中或刚取）或 -1（交给 CPU）；expert_recency[l, A] = step
    cpu_ids = where(ids >= 0, -1, raw)
    D2H(x, cpu_ids, w); memop: ready[l] = 1     # cpu_executor.py:543-587
    copy_missing(F)                              # H2D：f 个专家进入槽（进入 LRU 缓存）
    y_gpu = grouped_gemm(x, ids.clamp(0), w·[ids >= 0])  # 交给 CPU 的路由权重置零，仍按 10 路发射
    memop: wait done[l] ≥ 1; H2D(y_cpu)          # cpu_executor.py:589-605
    out = shared_gate_mul_add(y_gpu + y_cpu, sh)

CPU 侧（cpu_moe_ext.cpp）:
  协调线程自旋轮询 ready[l] → submit()：单线程把 x 反交错并量化成 int8；
    task_cv.notify_all() 唤醒 21 个在 condition_variable 上睡眠的工作线程          # :1876, :1961
  协调线程 sync()：在 sync_cv 上睡眠，等全部工作线程完成                          # :1964-1968
  工作线程：pass1（gate_up，按 32 行切）→ 自旋屏障 → prep → 屏障 → pass2（down，按 32 行切，对路由求和）  # :1843-1866
  最后一个完成的线程 notify sync_cv → 协调线程设 done[l] = 1
  NUMA：代码假定单节点（:1102-1103 注释）；retry2 实际用 numactl --interleave=all
```

### 1.2 Strata（v0.1.41，fb58e0d）

```text
启动:
  GPU 专家缓存 = expert-profile.bin（按路由频次排序）从最热往下填，填满可用显存
    # S1：9,196 槽，17.45 GiB（实测 stderr:15）；KV int8，常驻 32K
  pcie_frac：原生包默认 0.55，链路实测低于 20 GB/s 时按比例缩小；S1 为 0          # generate.cpp:555, 1556-1558, 2454-2471
  自适应层：每 4 个窗口，按衰减 0.7 的热度最多换 96 个专家；换入至少滞后 1 个窗口生效    # generate.cpp:559-560, 586；DETAILS.md:264-266
    # S1 用 --adapt-every 100000 --adapt-swaps 0 关闭

每个校验窗口（S1：T = 1，不起草稿）:
  for l in 0..47:
    GPU：注意力/GDN、路由、共享专家
    主机：读 ids；usage[l,e] += 1（热度）                                        # expert_source.cpp:3135-3137
    计划（主机端决定，先发布给 GPU）:                                             # expert_source.cpp:3139-3230
      本层去重后的专家：VRAM 命中 → GPU 组；
      未命中中按路由顺序最后 floor(nmiss*pcie_num/256) 个 → PCIe 份额
        （走 staging DMA 或映射别名直接读，不写入缓存）；
      其余 → CPU 池
    GPU 组内核（命中 + PCIe 份额）与 CPU 池（自旋工作线程，按 epoch 认领作业）同时计算
    合并部分和；残差链仍逐层串行（expert_cache.hpp:3-6："96% exposed"）
  路由预读：只用于文件层（mmap/SSD）预热下一层可能用到的页；内存常驻时不用于 GPU 预取   # DETAILS.md:224, 252-254
```

### 1.3 关键差异

| 维度 | FreeToken hybrid | Strata | 对速度的可能影响 |
|---|---|---|---|
| 拆分在哪里决定 | GPU 内核，可被图捕获（推断） | 主机线程每层决定（推断） | Strata 每层要往返主机，但两端都自旋；FT 无需主机决策 |
| PCIe 取数比例 | $r$=27.7%（并发带宽比），可取 0 个 | 固定比例 0.55×链路系数；S1 为 0 | 两者都不含固定开销项（§2.4） |
| 取哪几个 | 按"最近活跃"优先（复现的未命中优先入缓存） | 按路由顺序取最后几个 | FT 的选择同时是一条缓存准入规则 |
| 缓存替换 | 只有取来的专家进 LRU，在关键路径上 | 静态画像加异步频次置换；PCIe 份额不入缓存 | FT 的准入受节流，可能改变失误率（推断，未测） |
| 容量 | 2,700 槽，约 7.5 GB | 9,196 槽，17.45 GiB | 同一合成输入上，FT 的 LRU 命中 74.7%，Strata 静态 62–63%（实测）。槽数 3.4 倍仍不如 FT 的 LRU；在真实内容上容量才是杠杆（论文 §8.3 D15） |
| CPU 池唤醒 | 工作线程每层经 condvar 睡眠/唤醒，协调线程睡在 sync_cv | 有流量时自旋停泊 | FT 每层约 0.2 ms 固定开销的最可能来源（推断，§2.5） |
| 共享专家 | 在提交 CPU 之前算，不重叠 | 在 GPU 上（与 CPU 是否重叠未核） | FT 可以把共享专家挪到提交之后（§2.7 第 5 项） |
| NUMA | 假定单节点，交错放置 | 有绑核（`pool_affinity_linux.hpp`），NUMA 策略未核 | GLM 这类带宽受限模型影响大 |
| 预读 | 解码不预读 | 只给文件层预热页面 | 单路 hybrid 时 PCIe 约 86% 空闲（推算），有预取余量 |

### 1.4 文献中同类方法

只取"未命中专家在哪算、怎么拆、怎么并行"。下表"有损"指改变模型数学，而不是浮点舍入差异。

| 工作 | 未命中专家在哪算 | 拆分 / 决策规则 | 并行与重叠 | 缓存 / 预取 | 有损？ |
|---|---|---|---|---|---|
| FreeToken [1]（arXiv 2608.16157 §3.2） | 一部分取进缓存在 GPU 算，其余在 CPU 原地算 | $B_R=\max(B_H-B_P,0)$，令两路用时相等，得 $q^\star\approx m B_P/B_H$；取整后由替换策略选具体专家；**至少保留 1 次取数**；没有固定开销项 | "暴露的层延迟取两条并行分支中较慢的一条"，不含非 MoE 部分 | 全局 LRU | 否 |
| KTransformers（SOSP'25） | 路由专家在 CPU（AMX/AVX-512），注意力与共享专家在 GPU | 静态放置，解码时不按需取（即 $q=0$） | 兼容 CUDA Graph 的异步 CPU 任务；**Expert Deferral**：把部分专家的输出推迟到下一层残差，让 CPU 与 GPU 注意力重叠，吞吐最高 +1.45× | 静态 | **是**（精度下降 ≤0.5%） |
| Fiddler（ICLR'25） | 不在 GPU 的专家默认在 CPU 算（只搬激活不搬权重） | 按延迟模型逐专家决定：CPU 耗时随 token 数线性增长；GPU 为常数加搬运；小批选 CPU，大批搬到 GPU | 按层 | 离线按热度静态放置 | 否 |
| HybriMoE（DAC'25） | CPU 与 GPU 都算，未缓存专家可搬到 GPU | 每层预执行模拟：CPU、GPU、PCIe 三条时间线，贪心让总完成时间 $\max(\text{CPU},\text{GPU})$ 最小；GPU 先算高负载的已缓存专家，CPU 先算低负载的未缓存专家，PCIe 先搬高负载的未缓存专家 | 同层内三者并行 | 用后 3 层门控做按收益排序的预取；得分缓存 MRS，$S=\alpha\,\mathrm{TopP}(s)+(1-\alpha)S$；比 kTransformers 解码快 1.70× | 否 |
| MoE-Lightning | CPU 算注意力，权重分页搬到 GPU | 用分层 Roofline（HRM）搜索策略 | CGOPipe：CPU、GPU、I/O 流水（批处理吞吐） | — | 否 |
| MoE-Infinity | GPU（取数） | — | — | 按请求级激活矩阵预取与缓存 | 否 |
| Pre-gated MoE（ISCA'24） | GPU | 门控提前一层选出下一层专家 | 预取与本层计算重叠 | 预取 | **是**（要改门控并微调） |
| ProMoE / AdapMoE | GPU | AdapMoE 按敏感度减少激活专家 | 预取 | 学习型预测器；按层动态规划分配缓存 | ProMoE 否；AdapMoE **是** |
| DAOP（DATE'25） | 按序列激活模式在 CPU 与 GPU 间分配 | 数据感知分配 | 在 CPU 上提前预算预测到的专家 | — | 部分（"优雅降级"） |
| llama.cpp | `-ot exps=CPU` / `--n-cpu-moe N` 把专家静态放在 CPU，解码时 CPU 算 | 批量 ≥ 约 32 时（op offload）把 CPU 上的权重拷到 GPU 算（社区资料，未核代码） | 按层 | 静态 | 否 |
| arXiv 2606.10493 | CPU（AVX-512 FP8 GEMV）加 GPU | 未给出逐专家规则 | **双批注意力与 MoE 交错重叠**（批 A 的 CPU MoE 与批 B 的 GPU 注意力重叠），吞吐 +50% | — | 否 |
| Strata | CPU 原地算，可配 PCIe 份额 | 固定比例 `pcie_frac` | 同层 GPU 命中与 CPU 并行 | 画像加频次置换 | 否 |

对本项目的含义：
- 用户已裁定先只走无损路线，所以 Expert Deferral、Pre-gated、AdapMoE 都不采纳。
- 可借鉴的无损做法有三项：
  - HybriMoE 的"按时间线模拟或闭式求解逐层拆分"（对应 §2.3）；
  - 2606.10493 的双批交错（对应 §2.6 两路）；
  - 利用空闲 PCIe 做下一层预取（只改放置，不改数学）。

---

## 2. 成本模型

### 2.1 结构事实：为什么不能写成 max(F, CPU)

- FreeToken 每层（推断，读码）：`decode_submit` → `copy_missing` → `_expert_gemm` → `decode_sync` → 相加，全在同一条 CUDA 流上，被捕获进同一张图（`layers/moe.py:328-383`）。第 $l+1$ 层的注意力依赖第 $l$ 层的输出。
  - 能与 CPU 并行的只有本层的取数和命中专家 GEMM（记为 $G$）。
  - 共享专家在提交 CPU 之前就算完了（`qwen4_exp/moe.py:22-24`），也不在重叠窗口内。
- Strata 自述（`include/strata/core/expert_cache.hpp:3-6`）：流水线只藏住 19.035 ms 中的 1.055 ms，CPU 工作 96% 暴露。
- 上游 [1] §3.2 的"层延迟 = 两条并发分支中较慢的一条"只描述 MoE 那一段，没有计入非 MoE 的串行部分，也没有固定开销（WebFetch 读 arXiv HTML 全文）。

### 2.2 一步耗时模型（建议写进论文）

第 $l$ 层有 $n_l$ 个未命中专家（批内并集），其中 $f_l$ 个经 PCIe 取到 GPU，其余在 CPU 算：

$$T_l(f_l)=\max\big(\,G_l+f_l\,t_P,\;\;O_C+(n_l-f_l)\,t_C\,\big)$$

$$t^{hyb}_{step}(B)=F'(B)+\sum_{l=1}^{48}\mathbb{E}\,[T_l]+\epsilon,\qquad F'(B)=t_0+kL+t_{req}(B-1)-\sum_l G_l$$

符号：
- $G_l$：本层 GPU 上 MoE 的固定部分（命中专家 GEMM 等），可与 CPU 重叠。
- $t_P=S/B_P$：每个专家经 PCIe 的时间。
- $t_C$：每个专家的 CPU 边际时间。
- $O_C$：每层 CPU 路径的固定开销，包括 D2H、标志位握手、线程唤醒、屏障、结果 H2D、相加。
- 对照：offload 的串行模型 $t^{off}_{step}=F(B)+\sum_l n_l t_P$，就是论文 §4.3 的形式（$G$ 已含在 $F$ 内）。
- FreeToken 即使 $n_l-f_l=0$ 也要付 $O_C$，因为 submit/sync 是捕获在图里的固定节点（推断）。
- 两者并发时 DMA 与 CPU 争用主存，此时用并发带宽：$t_P^{ov}=S/B_P^{ov}$，$t_C^{ov}=S/B_C^{ov}$。本机 benchbw 并发值为 15.64 / 40.85 GB/s（实测，几何为 7.97 MB 专家）。
- 主存读带宽下界（每步全部未命中字节都要从主存读出）：

$$t^{hyb}_{step}\ \ge\ F'(B)+\frac{B\,m\,S_{tok}}{B_M^{eff}},\qquad B_M^{eff}\approx B_P^{ov}+B_C^{ov}\ (\text{本机交错放置时约 }56.5\text{ GB/s})$$

### 2.3 最优拆分

把 $f$ 当成连续变量，两分支相等时取最小：

$$f^\*=\mathrm{clip}\!\left(\frac{O_C-G+n\,t_C}{t_P+t_C},\ 0,\ n\right),\qquad T^\*=\frac{t_P\,(O_C+n\,t_C)+t_C\,G}{t_P+t_C}\quad(\text{内点时})$$

- **取整**：比较 $\lfloor f^\*\rfloor$ 与 $\lceil f^\*\rceil$，取 $T$ 较小者。
- **是否调用 CPU**：若能跳过 CPU 调用（$f=n$ 时不付 $O_C$），则当且仅当 $O_C<G+n\,t_P$ 时 hybrid 在该层优于 offload；否则该层全部取到 GPU。
  - 上式与 $t_C$ 无关：只要拆分可以退化成全部取数，hybrid 不会比 offload 差。
  - FreeToken 现在不能跳过 CPU 调用，所以 $T\ge O_C$ 恒成立。
- **特例**：
  - $O_C=G=0$，$t_C=S/B_C$ → $f^\*=n\,B_P/(B_P+B_C)$。这是 FreeToken 代码用并发带宽时的规则：$r=B_P^{ov}/(B_P^{ov}+B_C^{ov})$（`bench_profile.py:185-187`）。
  - $O_C=G=0$，$t_C=S/(B_H-B_P)$（[1] 的"满竞争"假设）→ $f^\*=n\,B_P/B_H$，即 [1] 的 $q^\star$。
- **偏差**：现规则相对最优少取 $\Delta f=(O_C-G)/(t_P+t_C)$ 个。当 $O_C\gg G$ 时，规则系统性地取少了。
- **未计入的第二效应**：取来的专家进入 LRU，会改变未来的失误率；交给 CPU 的专家不进缓存。这需要实测（§2.7 第 1 项）。

### 2.4 与现有两条规则对照

| 规则 | 内容 | 与最优的关系 | 本机表现 |
|---|---|---|---|
| 取数比例（`offload_kernels.py:344-357`） | $f$ 取 $\lfloor nr\rfloor$ 或 $+1$ 中使 $\max(f(1-r),(n-f)r)$ 最小者 | $O_C=G=0$ 的特例；$n\le2$ 时 $f=0$。与 [1] 正文"至少保留 1 次取数"不一致（推断） | $r$=27.7%。按 $n\sim\mathrm{Binomial}(10,0.35)$ 推算，每层取约 0.77 个、CPU 算约 2.74 个（推算）。T09 实测计数为 0.62 / 2.43（另一配置） |
| 后端自动选择（`benchbw.py:598-600`） | 单独测得的 CPU 带宽 > 2 × PCIe 带宽 → hybrid | 静态阈值。用的是 8 MB 合成几何的单独带宽，不看失误率、批大小、$O_C$、$G$。按 [1] 自己的模型，阈值应为 1× | 比值 1.962，判 offload；但实测 hybrid 单路 +12%、两路 +49%，**判错** |

建议的判据与规则（推算，均无损）：
1. 启动时用实测的 $(t_P^{ov},t_C^{ov},O_C,G)$ 预算一张表 $f^\*(n)$（$n=0..k\cdot B$）。GPU 内核按 $n$ 查表，仍可被图捕获。
2. 后端选择改为比较 $\mathbb{E}_n[T^\*_{hyb}(n)]$ 与 $\mathbb{E}_n[G+n\,t_P]$，$n$ 的分布取自 D0 计数，并且按批大小 $B$ 分别判断。

### 2.5 参数与标定

| 参数 | 值 | 标签与来源 |
|---|---|---|
| $t_0$、$k$、$t_{req}$ | 13.1 ms、0.032 ms/千 token、5.3 ms | 实测拟合（论文 §4.3，第 0 代） |
| $t_P$ | 0.1141 ms / 2.77 MB（单独）；0.177 ms（与 CPU 并发） | 实测：`theory_v55.py`；并发值由 benchbw 15.64 GB/s 推算 |
| $t_C$ 的带宽上限 | 0.058 ms（47.62 GB/s 单独）；0.068 ms（40.85 GB/s 并发） | 由实测 benchbw 推算（几何为 7.97 MB 专家；Qwen3.8 的 2.77 MB 专家每次调用更小，效率可能更低） |
| 失误率 $m$ | 单路 35.08%；两路共享 38.24% | 实测 offload D0（retry2 RESULT_REPORT；论文 §4.7）。**hybrid 自身的失误率未测**（retry2 关闭了 D0） |
| $G$ | 0.02–0.08 ms/层 | 假设（命中 10 个专家的 NVFP4 GEMV 约读 27.7 MB 显存） |
| hybrid 实测 | 单路 33.83；两路 25.33 / 25.48 | 实测（retry2 window01） |

**两点标定**（脚本 `hybrid_model2.py`，推算）：用单路 33.83 解出 $O_C$，再预测两路，看能否得到 25.4。

| $t_C$（ms） | 由单路解出的 $O_C$（ms/层） | 两路预测（$m_2$=38.24%） | 让两路命中 25.4 所需的 hybrid 两路失误率 |
|---|---|---|---|
| 0.0445 | 0.260 | 25.4 | 38.2% |
| 0.058 | 0.223 | 24.2 | 约 34% |
| 0.068（$t_P$=0.177） | 0.196 | 23.4 | 约 31% |
| 0.097（Strata 拟合值按字节换算） | 0.116 | 21.3 | <30% |
| 0.22（主会话值） | 负数，不可行 | — | — |

读法：
- 无论取哪组，**$O_C$ 都在 0.19–0.26 ms/层**（每步 9–12.5 ms），是单项最大的可削减开销。
- 若 $t_C$ 取 benchbw 一致的值（0.058–0.068），还要求 hybrid 两路失误率比 offload 低 4–7 个百分点。这有可能成立：hybrid 只放约 25% 的未命中入缓存，而且优先放复现的专家，两路互相挤占会减轻（推断，待 hybrid D0 实测）。
- 主会话的"步级重叠"模型 $t=\max(F+\sum f t_P,\ \sum(n-f)t_C)$ 配 $t_C$=0.20 / 0.22 / 0.24 时：单路 38.0 / 34.5 / 31.7，**两路 18.1 / 16.4 / 15.1**，实测为 25.4。两路检查不通过。
- 样本外检查（R048b S 臂，32K，计数 CPU 2.43、PCIe 0.62）：$F'=14.13-1.92$，每层 $\max(0.111,\ 0.26+2.43\times0.0445)=0.368$，推算 33.5 tok/s，实测 31.94（模型为实测的 105%）。

对 Strata 的同一模型（推算）：
- S1 在 32K 时约 63 tok/s（实测），即 15.9 ms；每步约 180 个专家在 CPU 算。
- 若斜率为 0.045–0.071 ms，CPU 边际为 8–13 ms，串行加固定部分为 3–8 ms。
- 所以 Strata 与 FreeToken 的 CPU 边际代价同一量级，差在固定部分。

### 2.6 理论值对照（主会话指定参数）

$t_P$=0.114，$G$=0.04；单路 $m$=35.08%，两路 $m$=38.24%；$F=13.1$ 或 $14.0$（两路再加 5.3）；$O_C=0$（脚本 `hybrid_table.py`，推算，单位 tok/s）。

| $t_C$ | $F$ | 步级重叠模型（主会话）<br>单路 规则/最优 | 同左<br>两路每路 规则/最优 | 串行链模型（本文）<br>单路 规则/最优 | 同左<br>两路每路 规则/最优 |
|---|---|---|---|---|---|
| 0.071 | 13.1 | 57.8 / 76.3 | 34.8 / 43.2 | 48.3 / 49.2 | 29.2 / 30.2 |
| 0.071 | 14.0 | 55.0 / 71.4 | 33.7 / 42.6 | 46.3 / 47.1 | 28.5 / 29.4 |
| 0.22 | 13.1 | 34.5 / 47.0 | 16.4 / 25.2 | 24.9 / 37.2 | 13.3 / 21.5 |
| 0.22 | 14.0 | 34.5 / 45.7 | 16.4 / 24.8 | 24.4 / 36.0 | 13.1 / 21.1 |
| **实测** | | **33.83** | **25.33–25.48** | **33.83** | **25.33–25.48** |

读法：
- 两组 $t_C$ 在 $O_C=0$ 时都对不上实测。
  - $t_C$=0.071 时，单路偏高 40% 以上，说明存在 $O_C$；
  - $t_C$=0.22 时，两路偏低 35%，被排除。
- 加入 $O_C$ 后（§2.5），串行链模型能同时对上单路、两路和样本外点。
- 与 Strata 约 62 对照：FreeToken 现有 $F'\approx11.2$ ms。即使 $O_C\to0$，串行链模型下单路上限约 46–50 tok/s。要到约 62，还需把 GPU 串行部分削减约 4 ms：$O_C$=0.02、按最优拆分、$F'$ 减 4 ms 时推算 68 tok/s。

### 2.7 改进方向与推算收益（全部无损；按"先测后改"排序）

1. **先测**（D08 后续，不改默认路径）：
   - 在 hybrid 模式开 `--moe-collect-stats`，拿到每层的 missing、fetched、cpu 计数（`offload_cache.py:1269-1307` 已有）。
   - 给 CPU 路径打逐层时间戳：ready 标志置位 → 协调线程接手 → 工作线程开始 → pass1 结束 → pass2 结束 → done 标志 → GPU 等待结束。
   - 判据：$O_C$ 是否约 0.2 ms，以及它的构成。
2. **自旋线程池**：去掉每层的 condvar 唤醒，改用 epoch 自旋停泊（仿 Strata `pool.cpp`）；协调线程也参与计算；CPU 份额为空时不唤醒工作线程。
   - 推算：$O_C$ 从约 0.2 降到 ≤0.05 ms 时，单路 33.8 → 44–50，两路每路 25.4 → 27–32。
3. **带固定开销的拆分表** $f^\*(n)$：现有 $O_C$ 下单路 +6–12%、两路 +3–9%；第 2 项完成后约 0–2%。
4. **后端判据**改为 §2.4 的期望比较，替代 2× 阈值。
5. **把共享专家挪到 `decode_submit` 之后**，与 CPU 重叠：收益约等于每层共享专家 GEMV 时间 × 48（未测）。数学不变。
6. **利用空闲 PCIe 预取下一层**：单路 hybrid 时 PCIe 忙时约 $48\times0.77\times0.114\approx4.2$ ms / 29.6 ms，约 86% 空闲（推算）。可以用 Strata 式的"下一层路由作用于本层输入"来预测。准确率需要先离线测：要采集隐藏状态，现有 route trace 只有专家 id。
7. **两路**：保持批内合并。错相位交错（M4，或 2606.10493 的双批重叠）在批内已共享 $F$ 的情况下收益很小——$O_C$ 小时推算每路约 29 对批内 27–32（推算）。
8. **GPU 串行部分 $F'$**（13.1 ms 的构成）：这是 offload 与 hybrid 共同的最大剩余项，需要 profile。

---

## 3. 跨模型：GLM-5.3-Flash NVFP4

### 3.1 参数

- 42 个 MoE 层（45 层减去前 3 层稠密），top-8，每 token 激活 336 个专家（主会话给定）。
- 单专家：benchbw 预设几何 H=4096、I=2048，按 NVFP4 字节公式为 14,172,160 B ≈ 14.17 MB（推算，`benchbw.py:125-128` 与 `offload_cache.py:107`）。
- GPU 约放 530 个专家，占 4.4%；全未命中时每 token 4.76 GB，PCIe 搬运 196 ms（推算）。
- $t_P$=0.583 ms（单独）/ 0.906 ms（并发）；$t_C$=0.347 ms（40.85 GB/s 并发）/ 0.298 ms（47.62 GB/s 单独）。GLM 几何的实测 benchbw 尚无，可用代码已有的 `ft bench bw --model glm5.3-flash-nvfp4` 补测（本次不运行）。
- 没有 GLM 的实测失误率。按 Qwen3.8 在 11% 槽位时失误率 25–39% 外推，4.4% 槽位取 55–85%（假设）。
- GPU 串行部分 $F$ 未测，取 15–25 ms（假设）。

### 3.2 理论值（推算，$F$=20 ms；脚本内联）

| $m$ | offload 单路 | hybrid 单路<br>$O_C$=0.03 最优 / 规则 | hybrid 单路<br>$O_C$=0.26 | 主存上界<br>（56.5 GB/s） | 两路每路<br>offload / hybrid |
|---|---|---|---|---|---|
| 55% | 7.8 | 14.3 / 14.3 | 13.0 | 15.1 | 4.2 / 8.4 |
| 70% | 6.4 | 12.1 / 12.1 | 11.1 | 12.7 | 3.3 / 6.9 |
| 85% | 5.4 | 10.5 / 10.5 | 9.9 | 10.9 | 2.8 / 5.9 |

$F$ 取 15 或 25 ms 时，各值约变动 ±6%（见 `hybrid_model2.py` 输出）。

### 3.3 回答

- **offload 与 hybrid 的理论值**：
  - 单路：offload 约 5.4–7.8 tok/s，hybrid 约 10–14 tok/s，约 1.8–2.0 倍；
  - 两路每路：约 3–4 对 6–8 tok/s。
- **谁先成为瓶颈**：
  - offload 是 PCIe：24.3 GB/s，每 token 3.3 GB 时搬运约 137 ms。
  - hybrid 在 CPU 承担约 70% 的未命中后，瓶颈变成 DMA 与 CPU 共用的主存读带宽。本机交错放置下 benchbw 并发合计约 56.5 GB/s，hybrid 已达上界的 95% 左右。
  - 继续提速要靠 NUMA 本地化。论文表 4 的 STREAM：只绑 node1 为 110.8 GB/s，交错为 46.6 GB/s。171 GB 的专家池放不下两份副本，但可以按插槽分片，由本插槽的线程计算本插槽的专家（推断）。
  - 对照 Qwen3.8 单路：两者都不是瓶颈，固定开销才是。
- **两份数据能否支持"把 hybrid 做好，换模型后一样受益"**：方向上支持，而且 GLM 的相对收益更大，但需要满足以下条件（推算或推断）：
  1. **$t_C(S)\approx o_e+S/B_C^{eff}(S)$，且 $o_e$ 远小于 $S/B_C$。** 大专家的切块更均衡：pass1 按 32 行切，Qwen3.8 的 I=640 每个专家只有 20 块，GLM 的 I=2048 有 64 块。所以 $B_C^{eff}$ 随 $S$ 上升，单专家字节越大，CPU 越接近带宽极限。
  2. **每层固定开销 $O_C$ 远小于 $(n-f)\,t_C$。** GLM 每层 CPU 部分约 $4\times0.35\approx1.4$ ms，远大于 0.26，即使不修固定开销也只少 5–9%；Qwen3.8 每层约 $2.7\times0.06\approx0.16$ ms，小于 0.26，固定开销占主导。
  3. **在 DMA 竞争下 $B_C^{ov}$ 仍不低于 $B_P^{ov}$**：本机 40.85 对 15.64（8 MB 几何），需要用 GLM 几何复测。
  4. **主存容量与 NUMA**：171 GB 锁页只能放一份，CPU 带宽受交错放置与 UPI 限制。
  5. **$F_{GLM}$ 不能太大**：$F$ 越大，hybrid 的相对收益越被稀释。
  6. **数值**：hybrid 与 offload 不逐位一致，两个模型都一样。
- **结论**：真正随模型迁移的"做好 hybrid"是带宽相关的几项——内核达到主存 roofline、NUMA 分片、考虑竞争的拆分、按期望耗时选后端。固定开销优化对 Qwen3.8 是第一优先，对 GLM 是次要，但做了也无害。

---

## 4. 论文核对

### 4.1 v5.5 中关于 hybrid 的说明与公式（`paper/src/body_v55.html`）

| 行 | 位置 | 原文要点 | 判定 |
|---|---|---|---|
| 27 | 摘要（中） | hybrid 两路每路 25.33–25.48 高于 offload 的 16.95–17.01 及链路上界 23.9；单路 33.83 对 30.17 | 数字为实测，但 offload 侧不是同一窗口（见 4.3 第 1 条） |
| 39 | 摘要 | hybrid 是继承自 FreeToken 的执行器；不逐位一致 | 正确 |
| 52 | 英文摘要 | "In the same window, the hybrid executor …" | 同第 27 行的问题 |
| 80 | §1.1 | "解码按测得的带宽，在 PCIe 搬运与 CPU 原地计算之间分配未命中专家" | 正确（[1] §3.2） |
| 105 | 表 1 C5 | hybrid 单路 +12%、两路 +49%；Strata 1.8 倍分解属推算 | 分解需重写（§2） |
| 126-128 | §2.1 | 引用 [1] §3.2：$B_H$ 为主机侧处理带宽，DMA 与 CPU 共用主存，PCIe 跑满时剩 $B_H-B_P$；$q^\star=mB_P/B_H$ | 与 [1] 一致（WebFetch 核对）。缺"至少保留 1 次取数"和"由替换策略选具体专家" |
| 155 | 表 3 | [1] 行列出 $q^\star$ | 正确 |
| 156 | 表 3 | "KT 可视为 $q=0$ 的特例" | 放置维度上成立；但漏了 KT 的 Expert Deferral（有损的跨层重叠） |
| 245 | §4.3 | 串行模型，假设 1 为"传输与计算串行相加" | 只适用于 offload；hybrid 没有对应项 |
| 259-260 | §4.4 | 简化情景下的 $\phi$ 与链路预算不等式 | 只约束链路；$\phi$ 没有与规则或实测对接 |
| 311-315 | §4.7 | $R_{serial},R_{overlap},R_{link}$；hybrid 上界 $R_{link}/(1-\phi)$ | 缺 hybrid 结构项和主存上界 |
| 528-529 | §7.7 | "同一窗口内依次起 offload 与 hybrid 服务"；把高于 23.9 解释为 $\phi$ | 措辞不准；$\phi$ 未实测 |
| 530-537 | §7.7 | 旧负结果、T09 计数 2.43 / 0.62、"每层约 6.7 MB 由固定延迟主导"待验证 | 本报告的推算支持"固定开销主导" |
| 596（表 12f） | §8.3 | hybrid 行"未建模" | 可用 §2.2 补上 |
| 607 | §8.3 | 能改变链路约束的方向之一是 hybrid | 正确 |
| 608-617 | §8.4 | 三项分解；每 CPU 专家 0.20–0.24 ms；"55–65 tok/s" | 与两路实测矛盾，需重写 |
| 664 | §11 | hybrid 结论 | 同上 |
| 691 | §12 | hybrid 数值局限 | 正确 |
| 742、799 | 附录 | E1-R002；hybrid 诊断挂点 `cpu_executor.py:92-141`、`cpu_moe_ext.cpp` 屏障 | 建议补上 condvar 唤醒位置 `:1876`、`:1961`、`:1964` |
| 870 | v5.5 变更记录 | 说明了 $\phi$、§7.7、§8.4 的改动 | — |

### 4.2 缺什么

1. **§4.3 / §4.7 没有 hybrid 的结构项**：缺 $t^{hyb}_{step}$、$O_C$、$G$ 和主存上界，表 12f 只能写"未建模"。
2. **§4.4 的 $\phi$ 只出现在链路不等式里**：
   - 没有给出 $\phi=1-\mathbb{E}[f]/\mathbb{E}[n]$ 的取值。按 $r$=27.7% 的规则推算约 0.78；
   - 没有说明 $\phi$ 本身由规则决定；
   - 没有说明 retry2 未实测 $\phi$；
   - $R_{link}/(1-\phi)$ 单路约 240、两路每路约 97 tok/s（推算：两路按规则 $\phi\approx0.75$），都不起约束作用，真正起约束作用的是 $O_C$ 和主存上界。
3. **没有区分"继承自 [1]"与"代码演化"**。[1] 的 $q^\star$ 与"至少 1 次取数"是论文内容；以下三项是代码独有：
   - 并发带宽比 27.7%；
   - 比例模式可以取 0 个；
   - 2× 自动选择阈值。
4. **§8.4 建立在步级重叠假设上**，与 Strata 自述的"96% 暴露"矛盾。
5. **相关工作缺少直接相关的几项**：Fiddler、HybriMoE、llama.cpp 的专家卸载、2606.10493 的双批重叠（已作为 [8] 引用，但没有与 hybrid 两路联系起来）、KT 的 Expert Deferral（有损，可作为对照说明本文只走无损路线）。
6. **hybrid 自身的失误率未测**，§7.7 "大部分未命中专家改在 CPU 上计算"所依据的计数来自另一配置（T09）。

### 4.3 上游 [1] 的核对结果

来源：arXiv:2608.16157 v1，2026-08-17；WebFetch 读 HTML 全文。
- 核心是带宽自适应执行，即 §3.2 "Decode Codesign: Semantic-Aware Expert Caching and $q^\star$ Policy"：
  - $\mathcal M=\mathcal F\,\dot\cup\,\mathcal C$，$q=|\mathcal F|$；
  - 式(2) $B_R=\max(B_H-B_P,0)$；
  - 式(3) $T_{fill}(q)\approx qS/B_P$，$T_{cpu}(m-q)\approx(m-q)S/(B_H-B_P)$；
  - 式(4) $q^\star\approx mB_P/B_H$；
  - 取整后由替换策略选具体专家；"始终至少保留一次取数，使缓存持续预热"；$B_H\to B_P$ 时退化为纯按需取数。
- 表 1 中 RTX 4090 租用服务器：$B_P$=25.1，$B_H$=63.2 GB/s（$q^\star/m\approx0.40$）。
- 正文没有固定开销项，没有 2× 阈值，也没有 $q^\star$ 对比纯 offload / 纯 CPU 的解码实测，没有讨论多请求。
- 本文对 [1] 的引用（§2.1、表 3）在公式上是正确的。需要补充：
  - 上述代码与论文的差异；
  - 我们机器上的 $B_H$ 实测为 47.62，并发时 40.85；
  - 我们新增的部分：结构项、固定开销、最优拆分、主存上界、两路实测。

另外两处与事实不符：
1. **§7.7、摘要、表 5b 中"同一窗口"或"retry2 offload"的说法**：
   - offload 单路 30.17 来自 `development/d08_d10_gpu_window_retry1_20261011/evidence/window02/offload_single/`；
   - 两路 16.95 / 17.01 来自 2026-10-10 夜的闭环 X 组；
   - retry2 的 `RESULT_REPORT.md` 原文："these are historical reference comparisons, not a same-window causal isolation of executor effects. The offload single 30.1709957405 reference was reused as instructed."
   - 建议改为"同夜相邻窗口的 offload 参照"。
2. **表 3 的 Strata 行与 §8.4 的"`--pcie-frac 0`"**：应注明 S1 是 Strata 的可复现配置，不是其默认速度配置。

### 4.4 建议补进论文的草稿（只写草稿，不改论文文件）

**§4.3 末尾新增"hybrid 结构项"**（推导）

> hybrid 中，第 $l$ 层有 $n_l$ 个未命中专家，其中 $f_l$ 个经 PCIe 取进缓存、在 GPU 上计算，其余 $n_l-f_l$ 个在 CPU 上原地计算。单路解码时，下一层依赖本层输出：CPU 计算只能与本层 GPU 的 MoE 部分（命中专家与刚取到的专家，记为 $G_l$）重叠，不能与注意力等串行部分重叠（`layers/moe.py:328-383`；Strata 源码亦称其 CPU 工作 96% 暴露）。因此
> $$t^{hyb}_{step}(B)\approx F'(B)+\sum_l\max\big(G_l+f_l\,t_P,\;O_C+(n_l-f_l)\,t_C\big),\quad F'(B)=t_0+kL+t_{req}(B-1)-\sum_l G_l,$$
> 其中 $t_P=S/B_P$，$t_C$ 为每个 CPU 专家的边际时间，$O_C$ 为每层 CPU 路径的固定开销（D2H、握手、线程唤醒、屏障、结果回传）。并发时 $t_P$、$t_C$ 取 DMA 与 CPU 同时运行时测得的带宽。所有未命中字节都从主存读出，故还有 $t^{hyb}_{step}\ge F'(B)+B\,m\,S_{tok}/B_M^{eff}$。

**§4.4 的 $\phi$ 对接**（推导）

> $\phi=1-\mathbb E[f]/\mathbb E[n]$ 由取数规则决定，不是独立参数。按发布配置的比例 $r$=27.7%（benchbw 并发带宽比）推算，$\phi\approx0.78$；此时 $R_{link}/(1-\phi)$ 远高于实测，起约束作用的是 $O_C$ 与主存上界，而不是链路。retry2 未开计数，$\phi$ 的实测值待补。

**§4.7 新增"最优拆分"**（推导）

> 令两分支相等，得 $f^\*=\mathrm{clip}\big((O_C-G+n\,t_C)/(t_P+t_C),0,n\big)$。[1] 的 $q^\star=mB_P/B_H$ 是 $O_C=G=0$、$t_C=S/(B_H-B_P)$ 时的特例；发布代码以并发带宽比 $r=B_P^{ov}/(B_P^{ov}+B_C^{ov})$ 取数，同样忽略固定开销，每层少取 $(O_C-G)/(t_P+t_C)$ 个。若能在 $f=n$ 时跳过 CPU 调用，则 hybrid 在一层上优于 offload，当且仅当 $O_C<G+n\,t_P$。发布代码以"CPU 带宽 > 2 × PCIe 带宽"自动选择后端，这一阈值不在 [1] 中；本机比值为 1.962，判为 offload，而实测 hybrid 单路 +12%、两路每路 +49%。

**§7.7 改写首段措辞**

> 同夜相邻窗口（offload 单路 30.17 取自 retry1 window02；两路 16.95 / 17.01 取自 10-10 夜闭环 X 组；hybrid 取自 retry2 window01，参数仅改 `--moe-strategy hybrid` 与绑核）……本次 hybrid 未开计数，其失误率与取数比例未实测；按发布配置的比例规则推算，每层约 22% 的未命中经 PCIe 取到 GPU（推算）。

**§8.4 重写要点**（推算）

> 用 §4.3 的结构项，以 retry2 单路与两路两点标定：每层固定开销 $O_C\approx0.19$–$0.26$ ms（每步 9–12.5 ms），每 CPU 专家边际 0.04–0.07 ms（40–70 GB/s，与 benchbw 实测内核带宽 40.85–47.62 GB/s 同量级）；样本外点（R048b S 臂）模型为实测的 105%。由此，hybrid 单路 29.6 ms ≈ 串行部分 11.2 + 每层固定 9–12.5 + 边际 6–9。Strata 每专家边际同一量级（7 点拟合 0.045 ms / 2.04 MB），串行与固定部分约 3–8 ms。约 1.8 倍差距主要来自 FreeToken 的每层固定开销与更大的 GPU 串行部分；"每专家 0.20–0.24 ms"与两路实测不符，应撤回。量化在 PCIe 结构下约 +15% 的推算不变。

**表 3 增补行**

> Fiddler（CPU 算不在 GPU 的专家；按批大小的延迟模型决定）；HybriMoE（逐层模拟 CPU、GPU、PCIe 三条时间线的拆分；按门控预取）；llama.cpp（静态把专家放在 CPU，大批时拷到 GPU 计算）；KTransformers 的 Expert Deferral（跨层重叠，有损，本文不采用）；[8] 的双批注意力与 MoE 重叠（与两路 hybrid 的关系）。

---

## 5. 与主会话现有推算不一致的地方

| # | 主会话现有推算 | 本报告 | 依据 |
|---|---|---|---|
| 1 | FreeToken 每个 CPU 专家约 0.20–0.24 ms（11–14 GB/s），约为 Strata 的一半 | 边际约 0.04–0.07 ms，另有每层约 0.19–0.26 ms 固定开销；$t_C$=0.22 时两路预测 15–18 tok/s，实测 25.4 | §2.5（推算）；benchbw 内核 47.62 / 40.85 GB/s（实测） |
| 2 | 若改成 Strata 结构并达到其 CPU 效率，单路约 55–65 tok/s | 串行链模型下 $O_C\to0$ 约 44–50；到约 62 还需削减 GPU 串行部分约 4 ms | §2.1、§2.6（推算） |
| 3 | 差距主因是执行结构，其次是 CPU 执行器效率 | 主因是每层固定开销（CPU 池 condvar 唤醒等）与 GPU 串行部分；每专家带宽不是主因 | §2.5（推算）、§1.3（推断） |
| 4 | Strata 每专家 0.071 ms，截距 3.3 ms，处在 CPU 受限区间 | 3 点斜率不稳：7 点为 0.045 ms、截距 7.6；32K 4 点为 0.036 ms、截距 9.3；且 S1 是可复现配置 | stderr:23-80（实测）、S1 argv（实测） |
| 5 | "同窗口实测"：hybrid 对 offload | offload 单路来自 retry1 window02，两路来自 10-10 夜闭环 X | retry2 RESULT_REPORT（实测工件）。午后已有真正的同窗口 A/B（window02：+21% / +55%），见 §6.1 |
| 6 | 取数规则即 [1] 的 $q^\star$ | 代码用并发带宽比 27.7%，可取 0 个；[1] 正文要求至少 1 次；2× 阈值只在代码里，本机判 offload | §2.4、§4.3 |
| 7 | 两路 hybrid 的失误率沿用 offload 的 38.24% | hybrid 只放约 25% 的未命中入缓存，两路失误率可能低 4–7 个百分点；未测 | §2.5（推断） |

---

## 6. 午后补充：window02、KIMI 调研与 D08 诊断的对接

### 6.1 新的实测

**window02 同窗口 A/B**（服务器 `runs/dev_hybrid_verify_20261011/window02/`，`service_*/x_*/profile_export.jsonl` 中的 1000/ITL；`verdict.json`）：

| 项 | offload（O1、O2） | hybrid（H1） | 比值 |
|---|---|---|---|
| 单路 X | 30.15 / 29.62 / 30.19 / 29.67，均值 29.91 | 35.55 / 36.59，均值 36.07 | +20.6% |
| 两路每路 X | 16.81–16.98，均值 16.90（8 路次） | 25.96 / 26.12 / 26.11 / 26.27，均值 26.12 | +54.6% |

- H2 是新起、不预热的服务，单路 30.81。
- 同窗口 offload 单路为串行理论值 30.9 的 96.8%，两路为 16.58 的 102%（推算对比）。
- hybrid 单路在两个窗口之间相差 6.6%：retry2 为 33.83，window02 为 36.07。
- J4 为 affected：同一 hybrid 服务内重复同一请求，输出也不逐位一致。

**D08 诊断复核**（R048b S 臂，协调日志 2026-10-11T00:29:48；`plan/02_开发任务/D08_hybrid执行器诊断埋点.md:1`；`plan/D08_D10_GPU_TEST_DIRECTIVE_20261010.md:122-125`）：
- 每层 CPU 任务 = 0.207 ms 固定 + 0.084 ms × 专家数；
- 交给 CPU 的专家数为 0 时也要约 0.13–0.19 ms；
- 稳态 PCIe 份额：单路 0.205，两路 0.238。
- 以上为实测，但是在诊断模式下测得。

**KIMI 微基准**（`development/hybrid_code_research_20261011/MICROBENCH.md`；24 线程，合成 NVFP4，pageable 内存，不含 D2H/H2D 与标志位握手）：
- 线程池空任务往返 0.075 ms；
- 每个专家的边际 $t_C$=0.072 ms；
- 单核每 MB：FreeToken 0.373 ms，Strata 0.253–0.296 ms。

### 6.2 与本报告模型的对接

1. **取数份额**：规则推算单路 0.218、两路 0.242–0.247，D08 诊断实测 0.205 / 0.238。规则模型得到实测印证，即 $\phi\approx0.79$（单路）、0.76（两路）。
2. **用 window02 重新标定**（脚本同 §2.5，推算）：
   - 两点自由拟合：$O_C$=0.20–0.25 ms/层，$t_C$=0.03–0.05 ms。
   - 把 $t_C$ 固定为实测 0.072（KIMI）或 0.084（D08），由单路 36.07 解得 $O_C$=0.146 或 0.114 ms/层；这时要对上两路 26.12，hybrid 两路失误率需约 **29–31%**，低于 offload 的 38.24%。
   - 合起来，$O_C$ 的区间修正为 **0.11–0.25 ms/层**，即每步 5.5–12 ms。
   - D08 诊断的 0.207 ms 是"CPU 任务时长"，并且在诊断模式下测得，比关键路径上的增量偏大。按 0.207 + 0.084·n 直接代入，单路推算约 31 tok/s，比 window02 实测低约 15%。
3. **一条可预登记的预测**（推算）：
   - hybrid 两路的失误率会明显低于 offload 两路（约 29–32% 对 38%）。原因：hybrid 每步只把约 24% 的未命中放进缓存，而且优先放"上一步也用到"的专家，两路之间的互相挤占大为减轻（推断）。
   - 单路 hybrid 的失误率应接近 offload 的 35%。
   - 验证办法：在 hybrid 下开 `--moe-collect-stats` 测一次（`offload_cache.py:1286-1307` 已输出 missing、fetched、cpu 的计数）。
4. **R048b 样本外检查**：
   - 用 retry2 标定时，模型为实测的 105%；用 window02 标定时为 113%。
   - 由于 hybrid 单路本身在不同窗口间相差约 7%，这项检查只有约 ±10% 的分辨力。v5.6 §8.4 的"推算 33.5、实测 31.94"应注明这一点。
5. **修正后的改进推算**（$t_C$=0.072–0.084，$t_P$=0.114–0.177，按 window02 标定）：

   | $O_C$ | 单路（规则 / 最优拆分） | 两路每路（规则 / 最优拆分） |
   |---|---|---|
   | 现值 0.11–0.15 | 36.1 / 37.6–40.8 | 26.2 / 26.8–29.2 |
   | 0.075（KIMI 线程池往返下限） | 38.6–41.2 / 39.6–44.2 | 27.4–28.8 / 28.0–30.6 |
   | 0.05 | 40.5–43.3 / 41.0–45.5 | 28.3–29.8 / 28.6–31.3 |
   | 0.02 | 42.4–46.1 / 42.7–47.5 | 29.4–31.0 / 29.5–32.2 |

   - KIMI 的线程池改造（P1 自旋池加 P2 预处理移出关键路径）只能消掉 $O_C$ 中的线程池部分。按 KIMI 的拆分（推断），D2H、握手、结果回传约占 0.05–0.1 ms，所以 P1+P2 之后 $O_C$ 现实上约 0.05–0.1。
   - 对应单路约 **40–46**、两路每路约 **28–31** tok/s（推算）。v5.6 §8.4 写的"44–50 / 27–32"应改成这组数。
   - 最优拆分的增益依赖 $t_P$：PCIe 不受 CPU 争用时（0.114）明显，满争用时（0.177）几乎为零。所以拆分表 $f^\*(n)$ 必须用并发实测的 $t_P$ 标定，否则可能多取。

### 6.3 与 KIMI 结论的一致与分歧

- **一致**：
  - 每专家边际代价两侧接近，"差 3 倍"不成立；
  - 主因是每层固定开销；
  - 首项改造是自旋线程池；
  - B≥2 时按专家去重（KIMI P3）对不同内容的两路收益有限，只限于两路未命中的交集部分。
- **分歧（只有一处）**：KIMI 把路由前瞻（RouterLookahead）列为不移植、低优先级，理由是 FreeToken 的取数决策已经在 GPU 上做。本报告的看法不同：
  - 单路 hybrid 时 PCIe 约 86% 空闲（推算，§2.7 第 6 项）；
  - 用空闲链路把下一层的预测专家提前取进缓存，是不改数学的提速；
  - 这一点 offload 做不到，因为 offload 的链路已经忙于按需取数。
  - 这与协调日志 00:29–00:36 用户裁定的无损候选顺序（η → 路由前瞻召回率）一致，前提是召回率实测足够高。

### 6.4 论文 v5.6 剩余的缺口

v5.6 已采纳的内容：§4.4 取数拆分规则、§7.7 改为跨窗口参照加同窗口 A/B、§8.4 一步结构与分解、§12 的 OOM 记录。仍需要改的是：

1. **§8.4 分解只引了本报告基于 retry2 的拟合。** 应补上：
   - D08 诊断实测（0.207 ms + 0.084 ms/专家，PCIe 份额 0.205 / 0.238）；
   - KIMI 微基准（线程池往返 0.075 ms，$t_C$=0.072 ms）；
   - 改用 window02 同窗口数据（36.07 / 26.12）重新标定，$O_C$ 写成 0.11–0.25 ms。
2. **"44–50 / 27–32"改为"40–46 / 28–31"**，并注明前提：线程池与握手两部分都压缩后 $O_C$ 约 0.05–0.1 ms。
3. **R048b 样本外检查**注明分辨力约 ±10%（hybrid 单路跨窗口相差 7%）。
4. **§4.7 / 表 5a 仍没有 hybrid 的理论值行。** 可以按 §2.2 的结构项加一行"hybrid（$O_C$ 标定值）"，单路 36、两路 26，并注明 $O_C$、$t_C$ 的来源。
5. **J4（不可自复现）可以补一句算法层面的解释与出路**：
   - 原因：同一专家落在 GPU 还是 CPU，取决于缓存的历史状态，两种设备舍入不同。
   - Strata 的可复现配置正是"静态驻留加不取数"（`--adapt-swaps 0 --pcie-frac 0`），代价是缓存不能自适应（其文档写明会降速）。
   - FreeToken 若要可复现的 hybrid，同类做法是冻结驻留集并把取数比例设为 0。代价可用回放器推算：失误率上升多少，就让 CPU 多算多少（未测）。

---

## 7. 参考文献与证据位置

### 代码（服务器，读码）

- FreeToken release-e2（481d3a7），`/data2/FreeToken/wt/release-e2/python/freetoken/`：
  - `moe/offload_cache.py:142-161`（decode_target、hybrid_max_fetch、hybrid_fetch_fraction）；`:213-222`（num_missing_full、expert_recency）；`:1213-1232`（ensure_experts_hybrid）；`:1269-1307`（hybrid 计数）。
  - `moe/offload_kernels.py:10-16`（按 recency 选择）；`:43-60`；`:128-183`（CPU 镜像）；`:291-410`（hybrid 内核；`:344-357` 取数上限；`:364-398` 选择与驱逐；`:400-410` 改写 ids 与更新 recency）。
  - `layers/moe.py:294-306`、`:328-383`（`_decode_hybrid`）。
  - `models/qwen4_exp/moe.py:19-26`（共享专家在路由专家之前）。
  - `moe/cpu_executor.py:1-16`、`:32-49`（标志位握手）、`:92-146`（线程与绑核）、`:543-605`（submit / sync）。
  - `kernel/csrc/cpu_moe/cpu_moe_ext.cpp:1089-1104`（切块与"假定单节点 NUMA"）、`:1568-1580`（屏障）、`:1843-1866`（run_task_body）、`:1869-1890`（worker_loop，condvar）、`:1892-1962`（submit，notify_all）、`:1964-1968`（sync）、`:2030-2066`（协调线程）。
  - `moe/benchbw.py:115-145`（工作负载，含 glm5.3、dtype nvfp4 3072×1536）、`:416-503`、`:539-595`（并发测量）、`:598-600`（2× 阈值）、`:659-679`。
  - `moe/bench_profile.py:114-153`、`:156-191`。
  - `engine/engine.py:725-756`、`:758-787`、`:1675`、`:1902-1946`。
  - profile：`/home/dell/.cache/freetoken/benchbw/GPU-052dcdb7-8f82-efdb-c9c0-8bef86e41efa.json`（2026-09-29）。
- Strata v0.1.41（fb58e0d），`/data2/Strata/wt/r002-v0141/`：
  - `include/strata/core/expert_cache.hpp:1-20`（96% 暴露；h_layer=0.0456）、`:40-60`（画像）。
  - `src/core/expert_source.cpp:3135-3230`（拆分计划）。
  - `src/program/generate.cpp:555`、`:559-560`、`:586`、`:619-623`、`:1550-1558`、`:2189-2195`、`:2454-2471`。
  - `src/kernels/cpu/pool.cpp:439-440`、`:491-535`（自旋停泊）。
  - `docs/HOW_IT_WORKS.md`；`docs/DETAILS.md:104-111`（`--pcie-frac 0` 用于可复现）、`:224`、`:252-254`（lookahead）、`:264-266`、`:290-294`（hit_rate 与 pcie_share 口径）；`docs/BATCHING.md`；`docs/DISJOINT_EXPERT_CACHE.md`。

### 实测工件

- `freetoken/development/d08_d10_gpu_retry2_20261011/RESULT_REPORT.md`；`evidence/window01/hybrid_service/serve.log:2,14,20-22`；`runtime_config.json`。
- `freetoken/development/d08_d10_gpu_window_retry1_20261011/evidence/window02/offload_single/`（offload 30.17）。
- `strata/development/r002_v0141_night_execution_20261009/receipt/S1.json`（argv）；服务器 `/data2/Strata/r002-prep/night_execution_20261009/raw-runs/v3-S1/stderr.log:15,23-80`。
- `freetoken/development/kimi_phase2_20261011/STAGE2_RESULT.md`（上午的 hybrid 复验 S3 为 failed_harness，无数据）；`EVENING_RESULT.md`（window02 机械判定）。
- 服务器 `/data2/FreeToken/runs/dev_hybrid_verify_20261011/window02/verdict.json`，以及 `service_{O1,H1,H2,O2}/x_{single,two}_*/profile_export.jsonl`（§6.1 的逐请求速度）。
- `freetoken/plan/02_开发任务/D08_hybrid执行器诊断埋点.md:1`、`plan/D08_D10_GPU_TEST_DIRECTIVE_20261010.md:122-125`、`plan/COORDINATION_LOG.md`（2026-10-11T00:29:48 条）：D08 诊断 0.207 + 0.084·n，PCIe 份额 0.205 / 0.238。
- `freetoken/development/hybrid_code_research_20261011/`：`MICROBENCH.md`、`Q1_Q10_COMPARISON.md`、`PORTABLE_IDEAS.md`、`CODE_MAP.md`（KIMI 代码调研与微基准）。
- 论文 `paper/src/body_v56.html:272`（§4.4 取数拆分规则）、`:529-532`（§7.7）、`:612-623`（§8.4）。
- 论文 `freetoken/paper/src/body_v55.html`（行号见 §4.1）；`paper/src/theory_v55.py`。

### 推算脚本（会话 scratchpad，未入仓库）

- `tools/hybrid_model.py`、`hybrid_model2.py`、`hybrid_table.py`：串行链模型、两点标定、策略对比、GLM 情景。
- 主要假设：$n\sim\mathrm{Binomial}(k\cdot B,m)$，各层独立；$G$ 取 0.02–0.08 ms；两路的 $F$ 用第 0 代 $t_{req}$。

### 文献

- [1] S. Yang et al., FreeToken: Efficient Edge-Native MoE Serving with Bandwidth-Adaptive Execution, arXiv:2608.16157, https://arxiv.org/abs/2608.16157（HTML：https://arxiv.org/html/2608.16157v1，§2.1、§3.2、§5.1 表 1、§5.3）
- KTransformers（SOSP'25）：https://madsys.cs.tsinghua.edu.cn/publication/ktransformers-unleashing-the-full-potential-of-cpu/gpu-hybrid-inference-for-moe-models/ ；Expert Deferral 说明：https://lmsys.org/blog/2025-10-22-KTransformers
- Fiddler: https://arxiv.org/abs/2402.07033
- HybriMoE: https://arxiv.org/abs/2504.05897
- DAOP: https://arxiv.org/abs/2501.10375
- arXiv 2606.10493（Cloud-Grade SLOs，双批重叠）：https://arxiv.org/abs/2606.10493
- llama.cpp 专家卸载与 op offload（社区指南，未核代码）：https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide
- MoE-Lightning arXiv:2411.11217；MoE-Infinity arXiv:2401.14361；Pre-gated MoE（ISCA'24）；ProMoE arXiv:2410.22134；AdapMoE arXiv:2408.10284（后三者按已知摘要概括，本次未重新打开全文）。
