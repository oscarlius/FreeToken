# 任务书：按 FreeToken 论文把单卡 Qwen3.8 的解码和冷 32K 首 token 再量一遍

日期：2026-10-03。执行人：其他 Agent。机器仍是 1×RTX 4090。四卡方案只写预估，不要做。

论文：https://arxiv.org/html/2608.16157v1  
依据：专家是整份进缓存；预填用整层双缓冲，算力被 PCIe 盖住；解码由失误率和主机带宽决定，\(q^\star \approx m \cdot B_P / B_H\)。本机当前启动用的是 `numactl --interleave=all`，论文在 4090 上是把线程绑在 GPU 所在 NUMA。

## 基线（已实测，不要重测 ExLlama）

同一模型 `Qwen3.8-Flash-Next-NVFP4`，关闭思考（`chat_template_kwargs.enable_thinking=false`）。

| 项 | 数字 | 出处 |
|---|---|---|
| 冷 32K 首 token | **21.52 s**（两轮 21.32 / 21.52，取慢的一轮） | `freetoken/RESULTS_FT_COLD32K_20261002.md` |
| 冷 32K 解码 | **37.52 tok/s**（37.13 / 37.91） | 同上，流式口径 \((n-1)/(t_{last}-t_{first})\) |
| 历史 33202 token 解码 | 35.10 tok/s | 面板生产格，口径可能与上一行不同，对照时注明 |
| 短上下文 C1 | 38.28 tok/s | 面板 |
| C2 / C4 聚合 | 63.34 / 96.57 tok/s | 面板 |

启动保持现有生产参数，除非某一项明确要改一项：`--memory-ratio 0.88`、`--ple-backend pinned`、`--moe-prefill-hit-d2d`、`--max-prefill-length 4096`、窗口三件套 49152、端口 **8095**。不要改量化，不要改成 PLE disk，不要开 TP。

## 预估（点估计，测完用第 0 步的实测替换）

专家池大约 68 GB（63 GiB），每个专家大约 2.76 MB（NVFP4，gate/up/down 共 3×2560×640），每 token 选 10 个专家 × 48 层。全失误时每个 token 大约读 **1.33 GB**。论文在同类 4090 上测到 \(B_P = 25.1\) GB/s、\(B_H = 63.2\) GB/s（6 线程、绑 GPU 的 NUMA）。本机拷贝曾到大约 95 GB/s，但是 20 线程，不是专家核。

冷 32K 现在 21.5 秒，`--max-prefill-length 4096` 时大约 8 个块。若每一块都把大部分专家池再搬一遍，首 token 大致随块数下降：

| 步骤 | 改什么 | 点估计 | 区间 | 保留条件 |
|---|---|---|---|---|
| 0 只测量 | 不改速度 | 解码仍约 37.5，首 token 仍约 21.5 s | — | 必须交出 \(B_H\)、\(B_P\)、失误率、每一块搬运的字节 |
| 1 NUMA | `interleave=all` 改为只绑 GPU 所在节点 | 冷 32K 解码 **48 tok/s** | 42–54 | ≥42 才保留，否则退回 interleave |
| 2 预填块 8192 | 只改 `--max-prefill-length 8192` | 冷首 token **11 s** | 9–16 | ≤14 s 且双缓冲仍在才保留 |
| 3 预填块 16384 | 仅当第 2 步已保留 | 冷首 token **6 s** | 5–10 | ≤10 s 才算首 token 目标达到；显存放不下两层缓冲就停 |
| 4 专家槽 | 在第 1 步之上，把让出来的 KV 变成专家槽（先记 dtype 和槽位数） | 冷 32K 解码 **52 tok/s** | 46–58 | 失误率至少下降 10 个百分点 |
| 5 MTP | 只使用已在显存里的专家 | **不计入默认预期** | 接受率 ≥80% 且失误率 <40% 时，在第 4 步结果上再 +8%（约 56） | 变慢或接受率 <70% 就关掉 |
| 6 两路并发 | 同一层相同专家只从主机读一次 | C2 聚合 **78 tok/s** | 68–90 | 每一路仍 ≥30 |
| 四卡（不做） | 四块缓存、会话钉卡、共享一份专家池 | 单路冷 32K 解码 **65 tok/s**，首 token **8 s** | 解码 55–80，首 token 5–12 | 硬件未到，标 BLOCKED |

第 1 步和第 4 步不要连乘。52 已经是两者叠在一起的点估计。第 5 步默认不叠加进交付数字。

第 0 步之后用实测改写点估计，不要死守 48：

\[
\text{tok/s} \approx 1 / \big(t_{\text{attn}} + \text{miss\_rate} \times 1.33\,\text{GB} / B_H\big)
\]

\[
\text{TTFT} \approx N_{\text{chunk}} \times \text{bytes\_per\_chunk} / B_P
\]

\(N_{\text{chunk}} = \lceil \text{prompt\_tokens} / \text{max-prefill-length} \rceil\)。若加长预填块后每一块的字节同比增加，首 token 不会下降，停止加长。

## 第 0 步（先做，不改参数）

用现在的 8095 进程。若进程不在，按 `RESULTS_FT_COLD32K_20261002.md` 里的命令拉起，思考关闭。

记录：

1. GPU 在哪个 NUMA 节点。`nvidia-smi topo -m`。
2. 专家核实际带宽 \(B_H\)（GB/s）和主机到这张卡的 \(B_P\)。用引擎自己的 profiler；没有的话，用与专家同样大小的读和 H2D 拷贝，线程绑在 GPU 那个节点上测一次，再按现在的 interleave 测一次。
3. 冷 32K 这一次生成的专家失误率、专家槽位数、KV dtype、是否走了整层双缓冲（还是退回按需加载）、每个预填块搬运的字节。
4. 把这四项写进结果。然后按上面两个公式重算第 1–3 步的点估计，写在结果开头，再开始改参数。

## 第 1–4 步怎么测

每一项只改一个因素。提示、计时与 `freetoken/TEST_TASK_FT_COLD32K_TTFT_20261002.md` 相同：冷前缀（换 id，禁止命中上一轮的前缀缓存）、temperature 0、max_tokens 128、`enable_thinking=false`、两轮取慢的一轮。解码用 \((n-1)/(t_{last}-t_{first})\)。首 token 是第一条正文 content，不是 reasoning。

顺序：第 0 步 → 第 1 步 → 第 2 步 →（有条件）第 3 步 → 第 4 步。第 5、6 步只有第 4 步保留之后才做。任一步不满足保留条件，就退回上一步的配置再往下，不要把失败项叠进最终命令。

质量：每一项保留时，用同一条短提示看 20 个 token 是否可读、有没有乱码。不要为了速度改量化。宣称替换生产配置之前，仍要用原来的 60 题，通过率不得低于 88.33%。本任务书的速度数字本身不自动替换生产锁定。

## 交付

结果写到 `freetoken/RESULTS_FT_PAPER_HEADROOM_20261003.md`。每一步：完整启动命令、改了哪一个参数、两轮原始时间、是否保留。

面板（覆盖同一格，备注里保留 21.52 s / 37.52 tok/s 和 35.10）：

```bash
curl -sS -X POST http://127.0.0.1:8098/api/benchmarks/record \
  -H 'Content-Type: application/json' \
  -d '{"model_id":"Qwen3.8-Flash-Next-NVFP4","framework":"ft","status":"TESTING","decode_tps":0,"ttft_s":0,"concurrency":"1","author":"task","source":"http_post","notes":"论文余量任务。冷32K。基线 TTFT 21.52 解码 37.52。本步点估计写在这里。"}'
```

最终若第 1 步保留而第 4 步没有，格子上的解码用第 1 步的慢轮，不要写成 52。

## 不要做

- 不要重启 ExLlama，不要占 8095 以外的推理端口。
- 不要做张量并行，不要上四张卡。
- 不要用更低比特，不要把 `--ple-backend` 改成 disk。
- 不要用短提示的 tok/s 宣称超过 35.10。
- 第 0 步没量到失误率和每一块字节数之前，不要改 `--max-prefill-length` 或 `--memory-ratio`。
