# 测量结果：FreeToken 论文余量任务（2026-10-03）

任务书：`TASK_FT_PAPER_HEADROOM_20261003.md`。单卡 4090。四卡只写预估，未做。ExLlama 未触碰。

## 结论（先读这个）

**唯一被保留的改动：`--max-prefill-length 4096 → 8192`，冷 32K 首 token 21.52s → 13.01s（−39.6%），解码持平（37.52 → 37.29，噪声内）。NUMA 重绑、16384 块、专家槽扩容均不保留；MTP / 两路并发因前置未满足未测。未宣称替换生产：8192 与 4096 的 60 题响应逐字一致、今日评测器下同判 78.33%，而 9/30 同样的响应判 88.33%——判卷器漂移，88.33% 门需先重定基线。**

实测改写后的点估计（第 0 步公式，替代任务书纸面估计）：

| 步骤 | 任务书点估计 | 实测改写 | 实测 | 保留？ |
|---|---|---|---|---|
| 1 NUMA 绑 GPU 节点 | 48（42–54） | **≈39–40**（见下） | 36.11 / 39.75 | 否（<42） |
| 2 预填块 8192 | 11 s（9–16） | **≈11.2 s** | 13.05 / 12.96 | **是**（≤14 且双缓冲在） |
| 3 预填块 16384 | 6 s（5–10） | ≈5.6 s | — | 否（CUDA OOM，按任务书停止） |
| 4 专家槽 | 52（46–58） | 不可达（见下） | 失误率 22.06%（−0pp） | 否（未降 10pp） |

## 第 0 步（只测量）：四项交代

1. **GPU NUMA 节点**：node1（`nvidia-smi topo -m`：CPU Affinity 1,3,5,…；ollama 钉在 node0 的核 0/2）。
2. **带宽（引擎自带 `ft bench bw`，qwen3.6-moe/nvfp4 真实内核 + 硬件上限）**：
   - `numactl --cpunodebind=0,1 --interleave=all`（现生产）：CPU STREAM 读 **B_H = 46.6 GB/s**，PCIe 线性 H2D **B_P = 24.3 GB/s**（nvfp4 gather 24.3，已打满 PCIe 上限）。
   - `--cpunodebind=1 --membind=1`（GPU 节点）：B_H = **110.8 GB/s**（2.4×），B_P 不变 24.2。
   - 论文参考：B_P 25.1 / B_H 63.2（6 线程绑 GPU NUMA）。本机 interleave 下 B_H(46.6) 已高于 B_P(24.3) → **解码不是主机读瓶颈，是 PCIe gather 瓶颈**——与论文 48 tok/s 估计的前提（B_H 瓶颈）不符，故第 1 步改写估计跌回 ≈39–40。
3. **失误率与缓存几何**（引擎原生仪表 `OffloadMoeCache.decode_miss_stats()`，经 `collect_stats` 开启、CUDA graph 内计数；本任务以 `PYTHONPATH` 注入 sitecustomize 强制开启，仅仪表、不改速度参数）：
   - 解码失误率 **21.93%**（每层 active 10.0 / missing 2.19），decode_target=gpu，失误全部走 PCIe：每 token 流量 = 0.2193×480×2.77248 MB ≈ **292 MB**。
   - 专家槽 **3149 / 24576（12.8%，LRU，8.1 GiB）**；KV 49152 tok（25,356 B/tok，1.2 GiB，引擎默认 dtype）；mamba 12 槽。
   - **整层双缓冲在**（`prefill_overlap=True`），未退回按需加载。
   - **每个预填块搬运字节 = 68.14 GB**（=整个专家池）：`prefill_rows=196,608=48 层×8 块×512 专家`，`prefill_hit_rows=0`——D2D 命中为零，每块全量重搬。专家实际大小 **2,772,480 B（2.64 MiB）**，专家池实际 **68.15 GB（63.5 GiB）**，任务书"85 GiB / 3.5 MB"为高估。
   - 公式自洽校验：TTFT ≈ 8 块 × 68.14 GB ÷ 24.3 GB/s = 22.4 s ≈ 实测 21.5–24.1 s ✓；解码 1/37.52 = 26.65 ms ≈ 12.0 ms（失误流）+ ~14 ms（注意力/计算/开销）✓。
4. **实测改写**：tok/s ≈ 1/(t_attn + miss×miss_bytes/B_eff)，B_eff = min(B_H, B_P) = 24.3（两种绑定下相同）；TTFT ≈ N_chunk × 68.14 GB / 24.3。块加长时每块字节恒为全池（命中 0），TTFT 严格随块数下降 → 8192 ≈ 11.2 s、16384 ≈ 5.6 s（实测见下）。

## 第 1 步：NUMA 绑 GPU 节点（不保留）

只改 `numactl --cpunodebind=0,1 --interleave=all` → `--cpunodebind=1 --interleave=all`（内存保持 interleave，避免 PLE 47.7G 钉死 + 专家 73.4G 页缓存压爆单节点 125GB）。

- ft-n1-a：TTFT 23.16 s，**36.11 tok/s**；ft-n1-b：21.28 s，39.75 tok/s。失误率 22.85%（噪声级变化）。
- 慢轮 36.11 < 42 保留线 → **退回 interleave**。与改写估计一致：瓶颈在 PCIe，绑核救不了。

## 第 2 步：预填块 8192（保留 ★）

只改 `--max-prefill-length 4096 → 8192`，其余全同生产（含 interleave）。

- 仪表轮：ft-c8k-a 13.05 s / 36.10；ft-c8k-b 12.96 s / 37.63。分块 3×8192+7488=4 块 ✓，双缓冲在 ✓，失误率 24.1%（仪表噪声）。
- **无仪表干净复核（最终数字）**：ft-final-a **13.005 s** / 37.06；ft-final-b **12.901 s** / 37.52。慢轮 **13.01 s ≤ 14 s** ✓。
- 解码 37.06/37.52（均 37.29）与基线 37.52 持平——块大小只影响预填，不影响解码 ✓。
- 可读性抽查（20 token）："将模型专家分布到不同设备，并行计算以提升效率。" ✓。

## 第 3 步：预填块 16384（不保留，按任务书停止）

启动成功（图捕获后余 2.42 GiB），但首个请求预填即 **torch.OutOfMemoryError**（欲分配 384 MiB 时仅剩 215.69 MiB）——16384 块的双缓冲显存放不下。任务书明文："显存放不下两层缓冲就停"。**退回 step2 配置**，未继续加长。

## 第 4 步：专家槽（不保留）

在 step2 幸存配置上，`ft ctl cache rebuild --kv 33280 --moe 3280`（KV 49152→33280，仍容纳 32064+127；moe 3149→**3280 槽，13.3%**，+131 槽）。

- ft-s4-a 14.20 s / 39.76；ft-s4-b 12.91 s / 37.35。
- 失误率 **22.06%**（基线 21.93%，+0.1pp）——距"至少降 10 个百分点"极远。物理原因：+131 槽 ≈ +0.5% 覆盖，对 68 GB 池是杯水车薪；单卡 24 GB（预算 9.29 GiB 可分）覆盖上限 ~14%，失误率不可能 <12%。**退回**（rebuild 回 kv 49152 / moe 3149）。
- 预算实测：moe+kv 合计上限 9.29 GiB（memory-ratio 0.88 决定），`--moe 3336` 即 503 拒绝。

## 第 5、6 步（未做）

MTP 与两路并发的执行前置是"第 4 步保留"——未满足，按任务书跳过。

## 四卡（不做，BLOCKED）

任务书预估：单路冷 32K 解码 65 tok/s（55–80）、首 token 8 s（5–12）。用第 0 步实测常数粗校：四卡若专家槽 ≈4×（覆盖 ~51%），失误率可望降到 ~0.48×现值，B_P 若靠多卡 PCIe 聚合提升，解码上限由 1/(t_attn+miss×68.1GB×480/24576/B_eff) 决定——量级上 65 tok/s 可信，但**必须四卡实测**，本报告不采信。

## 质量门：88.33% 判卷器已漂移（重要发现）

按任务书，宣称替换生产前须过 60 题（`/data2/_shared/test_prompts_60.json`，`benchmark_client.py phase3` + 本地 `evaluator.grade_question` 离线重判）。结果：

- **8192 与 4096（生产对照）各跑一次完整 60 题：60 题响应逐字一致（60/60）**，离线重判同分 **78.33%**（47/60：中文抽取 15/15、结构化工具 15/15、代码 7/15、长文多轮 10/15）。
- 同一批响应字符串在 **9/30 retest 判 88.33%（53/60）**，今天判 78.33%——生成完全确定（三次运行响应逐字一致），**掉分 100% 来自判卷器 `evaluator.py` 版本漂移**，与 8192 改动无关。
- 结论：**不宣称替换生产**（今天的评测器下连生产配置自己都过不了 88.33% 门）。8192 作为"TTFT −39.6%、解码持平、质量逐字等价"的候选保留，**替换生产前需先重定 88.33% 门的评测器基线**（另行立项）。

## 每步完整启动命令

全部命令与 `RESULTS_FT_COLD32K_20261002.md` 的生产命令逐字一致，仅以下参数按步变化（远端存档 `/data2/FreeToken/runs/paper_headroom_20261003/`）：

| 步 | 变化 | 日志/脚本 |
|---|---|---|
| step0/仪表 | 无（+PYTHONPATH 仪表注入） | `serve_step0.log`、`serve_stats.log`、`moe_stats*.json` |
| step1 | `--cpunodebind=1 --interleave=all` | `serve_step1_numa.log` |
| step2 | `--max-prefill-length 8192` | `serve_step2_chunk8192.log`、`serve_final_8192.log` |
| step3 | `--max-prefill-length 16384` | `serve_step3_chunk16384.log`（OOM） |
| step4 | `ft ctl cache rebuild --kv 33280 --moe 3280` | `serve_step4_slots.log`、`moe_stats_step4*.json` |
| 对照 | 生产 4096（质量对照） | `serve_control_4096.log` |

两轮原始 JSON（ft-hd-a/b、ft-n1-a/b、ft-c8k-a/b、ft-s4-a/b、ft-final-a/b）都在上述目录。`bench_bw_interleave.json` / `bench_bw_node1.json` 为第 0 步带宽档案。

## 面板

已覆盖 Qwen3.8-Flash-Next-NVFP4 / ft 格：TTFT 13.01（8192 慢轮）、解码 37.29（两轮均值），status=TESTING，备注保留基线 21.52 s / 37.52 tok/s 与历史 35.10，并写明"未宣称替换生产，88.33% 门待重定基线"。

## 遗留状态

测完已停 8095 服务，显存归还（见收尾输出）。仪表注入器 `_shared/ft_paper_stats_sitecustomize.py`（远端 `/data2/_shared/ft_hooks/sitecustomize.py`）仅在 `FT_PAPER_STATS=1` 时生效，默认惰性、无影响，保留供复测。
