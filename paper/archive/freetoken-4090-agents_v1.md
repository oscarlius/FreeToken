# 单张消费级 GPU 上的多会话 Agent 推理：FreeToken 二次开发的测量、模型与修改

> 状态：第 1 版留档（2026-10-03），不再修改。当前稿是 `freetoken-4090-agents_v2_draft.md`。

作者：（待定）

## 摘要

（草稿，随轮次更新）在一张 RTX 4090（24 GB）上服务 Qwen3.8-Flash-Next NVFP4：总参数约 125B，另有约 51B 的 N-gram 嵌入表；68 GB 专家池常驻主存，GPU 只缓存约 13% 的专家。目标负载是约 10 个 Agent 会话，单会话 64K 窗口，首 token ≤ 10 s，持续解码 > 30 tok/s。

我们在 FreeToken 之上做二次开发。层优先长预填把冷 32K 首 token 从 {{r:E0-R000.cold32k.ttft_s}} s 降到 {{r:E0-R006.cold32k.ttft_s.max}} s，输出与基线逐位一致。我们给出一个用本机实测校准的带宽/算力模型，并用它为每一项修改事先给出推算区间。

模型还指出单卡的瓶颈不在单会话，而在多会话：内容不同的两个会话同时生成时每路解码、一个会话的长预填对其他会话的停顿、以及会话 KV 无处安放（待 E1-R005 与第二阶段结果）。

## 1. 引言

### 1.1 问题

- 消费级单卡加主存专家池：每 token 激活 480 个专家（48 层 × top-10），未命中的专家要经 PCIe 搬运。
- Agent 负载：长上下文、多轮、中途编辑、多会话并发。体验线见上。
- FreeToken 论文针对单请求和单 NUMA 节点，没有覆盖多会话和本机的双路 CPU。

### 1.2 贡献（状态随轮次自动更新）

1. 测量方法：轮次、单变量、确定性门、推算区间对照（第 3 节）。
2. 用本机实测校准的性能模型，包括冷预填、解码与多会话（第 4 节）。
3. 层优先长预填 D1：{{v:E0-R006}}。
4. 预填内核移植（上游 #578）：{{v:E1-R001}}。
5. 多锚 GDN 检查点 D3：第一步 {{v:E0-R008}}，主体进行中。
6. 层间插解码 D6、主存会话层 D8：计划中。
7. 负结果汇总（第 7 节）。

## 2. 背景

### 2.1 FreeToken 的机制

- 主存专家池是唯一真相，GPU 上按（层，专家）整槽管理 LRU 缓存。
- 预填用整层双缓冲：GPU 算第 $l$ 层时，PCIe 搬第 $l+1$ 层的全部专家。
- 解码时 $m$ 个未命中按 $q^\star \approx m\,B_P/B_H$ 分成「搬进缓存」与「CPU 原地计算」两组并行。
- 整个解码步装进一个 CUDA Graph，路由相关控制在 GPU 上。

### 2.2 与 KTransformers 的关系

KTransformers 让 CPU 用 AMX 计算路由专家。本机 Xeon Silver 4310 没有 AMX，KT 只能退到 avx2 后端，约 3K 输入就显存不足。用统一公式看，KT 是 FreeToken 在「放置固定、所有未命中交给 CPU」下的特例。详见 `_shared/PAPER_COMPARE_KT_FT_20261003.md`。

### 2.3 模型结构

48 层：36 层 GDN 线性注意力，12 层 QSA 稀疏全注意力。每层 512 个专家、top-10，每个专家 $3 \times 2560 \times 640$ 参数，NVFP4 下 2,772,480 字节。第 2 层有 PLE（N-gram 嵌入，钉在主存）。

## 3. 平台与方法

### 3.1 平台

| 项 | 值 |
|---|---|
| GPU | 1 × RTX 4090 24 GB，PCIe 4.0 x16，挂在 NUMA node1 |
| CPU | 2 × Xeon Silver 4310（每路 12 核，AVX-512F + VNNI，无 AMX） |
| 主存 | 约 251 GiB |
| PCIe 专家搬运 $B_P$ | {{r:E0-R000.bandwidth.b_p_gbs}} GB/s |
| 主存 STREAM（交错 / 只绑 node1） | {{r:E0-R000.bandwidth.stream_interleave_gbs}} / {{r:E0-R000.bandwidth.stream_node1_gbs}} GB/s |
| 解码失误率（专家槽 12.8%，库内为比例值） | {{r:E0-R000.d0.miss_rate}} |

### 3.2 轮次方法

- 一轮 = 代码版本 + 启动命令 + 模型 + 运行状态，跑固定套件，给出判定。
- 基础代码换代时开新一代（epoch），只在同一代内比较增量。
- 一轮只改一个变量；首 token 两轮取慢的一轮，解码取均值；预期收益 ≤ 5% 的项按 ABAB 跑四次。
- 无损修改必须过确定性门：temperature 0 前 32 个输出 token、切块边界、每遍 H2D 字节与参照轮一致。
- 每一轮事先给出推算区间；实测偏离点估计 20% 以上时先修正模型，再进下一轮。

### 3.3 测试套件与口径

- S1-lite：冷 32K 两轮（换前缀）、短上下文解码、确定性门。
- S1：S1-lite + 64K + Agent 回放 + 两路不同上下文并发 + 停顿测试 + 60 题 + 30 分钟稳定性。
- S2：10 会话 Agent 回放，记录达标率（首 token ≤ 10 s 且解码 ≥ 30 的轮次占比）。
- 解码 = $(n-1)/(t_{last}-t_{first})$；冷首 token 必须换前缀。

## 4. 性能模型

### 4.1 冷预填（层优先）

$$
T(N) \approx \max\!\Big(\frac{P}{B_P}(1-h),\ \frac{aN}{s} + bN + cN^2\Big) + t_0
$$

$P$ 为专家池字节，$h$ 为预填 D2D 命中比例，$s$ 为 MoE 内核加速倍数。本机拟合 $a = 0.294$、$b = 0.042$ s/千 token，$c = 0.00181$ s/千 token²，$t_0 = 0.2$ s（由 E0-R006 拟合，E1-R000 后重拟合）。

### 4.2 解码

$$
t_{step}(B, L) \approx t_0 + kL + t_{req}(B-1) + B\,\frac{m\,S_{tok}}{BW}
$$

$S_{tok}$ 为每 token 全失误字节（1.331 GB），$BW$ 为未命中专家的处理带宽。本机拟合 $t_0 = 13.1$ ms，$k = 0.032$ ms/千 token，$t_{req} = 5.3$ ms。

### 4.3 校准

| 测点 | 推算 | 实测 |
|---|---|---|
| 冷 32K 首 token，层优先 | 12.8 s | {{r:E0-R006.cold32k.ttft_s}} s |
| 冷 32K 首 token，4096 分块（8 遍整池） | 22.4 s | {{r:E0-R000.cold32k.ttft_s}} s |
| 解码，32K 上下文 | 38.3 tok/s | {{r:E0-R006.cold32k.decode_tps}} tok/s |
| 64K 首 token / 解码（拟合点） | 29.9 s / 36.8 tok/s | {{r:E0-R006.ctx64k.ttft_s}} s / {{r:E0-R006.ctx64k.decode_tps}} tok/s |

（待补：C2/C4 与「路由独立」假设不符的分析，等 E1-R005。）

## 5. 修改与结果

每一小节固定写：动机（改的是模型里哪一项）、设计、推算、实测、判定、代码提交。

### 5.1 层优先长预填（D1）

- 动机：分块预填每块都要把整池搬一遍，8 块 × 2.80 s ≈ 22.4 s，与基线 {{r:E0-R000.cold32k.ttft_s}} s 吻合。
- 设计：层在外、子块在内，每层专家只搬一次；GDN 递归状态在层内子块间顺序传递。
- 实测：冷 32K {{r:E0-R006.cold32k.ttft_s}} s，64K {{r:E0-R006.ctx64k.ttft_s}} s，解码 {{r:E0-R006.cold32k.decode_tps}} tok/s。判定 {{v:E0-R006}}。
- 瓶颈转移到计算流：MoE 分组 GEMM 约 9.4 s，实效约 16 TFLOPS。
- 内部子块加大到 8192 能再快一点，但破坏逐位一致，判定 {{v:E0-R007}}。

### 5.2 预填内核（E1-R001，上游 #578）

- 实测（原推算为冷 32K 6.5–9.7 s、点 7.7 s，实际落在区间下沿之外）：层优先 + 4096 子块冷 32K 首 token {{r:E1-R001.groupA_pr_4096_layer.cold_ttft_s}} s，解码 {{r:E1-R001.groupA_pr_4096_layer.cold_decode_tps}} tok/s；不带层优先的对照组 {{r:E1-R001.groupB_pr_4096_no_layer.cold_ttft_s}} s，说明收益来自内核而不是分块。判定 {{v:E1-R001}}。
- 逐位一致：种子 7 重放对照 {{r:E1-R001.det_seed7.full_text}}（#578 组 {{r:E1-R001.det_seed7.pr_ttft_s}} s 对基线 {{r:E1-R001.det_seed7.base_ttft_s}} s）。
- 64K 没有读数：{{r:E1-R001.note_64k}}。

### 5.3 多锚 GDN 检查点（D3）

- 动机：GDN 是递归状态，前缀复用必须有对应位置的状态快照。
- 第一步实测（冷 / 中途编辑 / 整段重发）：{{r:E0-R008.agent.turn_ttft_s}} s。中途编辑零复用，根因是分块预填的中间块从不提交缓存。
- 每个轮次边界都切一段的方案更差：{{r:E0-R009.agent.turn_ttft_s}} s，判定 {{v:E0-R009}}。
- 主体（锚块中间提交、每请求多快照槽）进行中。

### 5.4 层间插解码（D6，计划）

（推算：他人最大字间隔从 16.7 s 降到 ≤ 1 s，预填方首 token +2%。）

### 5.5 主存会话层（D8，计划）

（推算：48K 被挤出会话恢复从约 21 s 降到约 3 s。）

### 5.6 CPU 分担未命中专家（E1-R002，计划）

（推算：单路 38–44 tok/s，两路不同上下文每路 25–34。）

## 6. 多会话评测（S2）

待第二阶段。

## 7. 负结果

- 只绑 NUMA node1：{{v:E0-R001}}，解码 {{r:E0-R001.cold32k.decode_tps}} tok/s。解码受 PCIe 限制，绑核无效。
- 预填块 16384：{{v:E0-R003}}，双缓冲显存放不下。
- 专家槽 +131 个：{{v:E0-R004}}，失误率（比例值）{{r:E0-R004.d0.miss_rate}}，基线（比例值）{{r:E0-R000.d0.miss_rate}}，覆盖率只多 0.5%。
- D1 内部子块 8192：{{v:E0-R007}}。
- D3 每轮边界切段：{{v:E0-R009}}。
- 判卷器漂移：同一批 60 题响应，9/30 判 88.33%，10/03 判 78.33%，生成逐字一致。质量门必须固定判卷器版本。
- 并发基准陷阱：同提示并发会让各路路由几乎相同，高估多会话吞吐（待 E1-R005 确认）。

## 8. 四卡部署推算

（第 4 节模型外推：4 进程共享主存专家池；常态每卡 1 路约 37 tok/s，峰值每卡 2 路约 21–23；4 卡同时整池预填受 UPI 限制。待硬件实测。）

## 9. 相关工作

- FreeToken，arXiv 2608.16157。
- KTransformers，SOSP 2025。
- （其余条目只收录核实过原文的工作。）

## 10. 结论

（待写。）

## 附录 A：轮次总表

{{table:rounds?epoch=0}}

## 附录 B：生产启动命令

```
numactl --cpunodebind=0,1 --interleave=all ft serve ... \
  --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d \
  --ple-backend pinned --moe-strategy offload --quant-backend moe.nvfp4=triton \
  --max-running-requests 2 --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 49152 --max-seq-len-override 49152 --max-prefill-length 4096 \
  --enable-cache-report --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder --reasoning-parser qwen3
```

完整命令见远端 `/data2/FreeToken/runs/cold32k_20261002/SERVE_CMD.txt`。

## 附录 C：复现

（待补：fork 地址、分支 `dev/d-series-clean`、各轮提交号、测试脚本路径。）
