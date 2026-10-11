# 给开发 Agent：参数任务已结束，下一步只做 D1

日期：2026-10-03。测量全文在 `freetoken/RESULTS_FT_PAPER_HEADROOM_20261003.md`。
方案原文在 `freetoken/DEV_PLAN_FT_QWEN38_20261003.md`。本文用实测改写优先级，冲突时以本文为准。

## 已经证明的事

冷 32K、关思考。保留配置是生产参数加上 `--max-prefill-length 8192`：首 token **13.01 s**（4096 时 21.52 s），解码 **37.29 tok/s**。16384 预填 OOM。专家槽从 3149 加到 3280，失误率 21.9% → 22.1%，无变化。只把进程从 `interleave=all` 改绑 NUMA node1，解码慢轮 36.11，低于保留线，已退回。

仪表：

- GPU 在 NUMA node1。STREAM 读：interleave 46.6 GB/s，只绑 node1 110.8 GB/s。PCIe H2D 始终 **24.3 GB/s**。
- 解码失误率 **21.93%**（每层 2.19/10）。每 token 有 **292 MB** 专家经 PCIe。单专家 2,772,480 字节。槽位 3149/24576（12.8%，8.1 GiB）。
- 预填 `prefill_overlap=True`，但 D2D 命中行数 = **0**。每一块搬 **68.14 GB = 整个专家池**。
- 8×68.14/24.3 ≈ 22.4 s，等于 4096 的首 token。4 块实测 13.01 s。公式成立。
- interleave 下 STREAM/PCIe = 1.92，低于 `ft bench bw` 默认 2 倍混合阈值。失误专家整段走 PCIe，所以只改绑核不会让解码变快。

8192 与 4096 的 60 题输出逐字相同。今日评测器两者都是 78.33%；9/30 的 88.33% 是旧判卷器。不要为了凑 88.33% 改模型。

## 开发顺序

**现在只做 D1（层优先长预填）。** D2 先不要写分配器。

### D1

现状：`begin_prefill()` 每个 token 块重置双缓冲，`prefetch_prefill_layer` 每块每层从主机再搬整层。命中缓存的专家在预填里是 0 行。

改法：同一层先吃完这条请求的所有 token 块，再进下一层。整次冷 32K 只搬一轮 68.14 GB。

点估计：68.14/24.3 = **2.80 s** 搬运。8192 的 4 块用了 13.01 s，合每块 3.25 s，其中约 0.45 s 不是纯搬运。层优先若这笔开销只付一次，冷 32K 首 token **约 6 s（4.5–8）**。解码应保持 37 tok/s 附近。

约束：

- 32K 层间激活约 0.7 GB，64K 约 1.4 GB（含 4 路 gated residual）。放不下就退回一次处理 2 块或 4 块，并写日志。
- 同一层内的 token 块必须按顺序走，GDN 状态和 QSA 的 KV 才能接上。
- 预填期间先允许独占 GPU。量正在解码的另一路的最大字间间隔；超过 3 秒再考虑层间插入解码。
- 开关默认关闭。temperature 0 下，新旧路径前 64 个输出 token 必须相同。
- 验收：冷 32K 首 token ≤ 9 s（两轮取慢）；解码不低于 37.29 的 97%；64K 不 OOM。

### D2（先测量，先不改分配器）

参数任务没有否定 D2，因为它没重算 fetch fraction。interleave 的 STREAM/PCIe < 2，服务不会走 CPU 混合。

下一小步只做这个：在 **只绑 node1** 的前提下跑 `ft bench bw` 的 **CpuMoeExecutor GEMV**（不是 STREAM），把 overlap 后的 `cpu_moe_overlap_gbs` / `pcie_gather_overlap_gbs` 写进该 GPU 的 profile，再开一次服务测冷 32K。

- GEMV ≥ 50 GB/s 且解码 ≥ 42 tok/s：再做 NUMA 分片（每个专家的 K 维按节点切开，两路只读本地内存）。点估计 **45 tok/s（40–52）**。
- GEMV < 40 GB/s，或重算 fraction 后解码仍低于 40：D2 停。解码的 292 MB/token 继续走 PCIe，天花板约 24.3 GB/s，单靠 CPU 绑核抬不上去。

### 先不要做

D3 多锚检查点、D4 专家去重、D5 MTP、四卡、16384 预填块、再加专家槽、更低比特、PLE disk、张量并行。
