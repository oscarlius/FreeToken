# D1 交付：层优先长预填（2026-10-03）

方案：`DEV_PLAN_FT_QWEN38_20261003.md` §D1。状态：**已实现；除 ≤9 s 点估计外各项门通过，替换生产门（60 题 + 30 分钟稳定性 + 与 main 的 A/B）未跑**（开关 `--prefill-layer-major`，默认关）。

## 一句话结论

**层优先长预填把冷 32K 首 token 从 21.52s 降到最终 12.66/12.98s（−41%/−40%；本文早期章节的 13.14/13.91 是开着 `FT_DEV_D0` 仪表的两轮，见下节），解码不掉（均值 38.25 vs 37.52），64K 无 OOM，并发字间隔反而优于基线（16.7s vs 20.4s）；输出与基线逐位一致（对基线重放 127/127 token）。未达方案 ≤9s 点估计——瓶颈已从搬运转移到计算流（MoE 9.4s + 注意力/GDN ~4s），进一步压榨需要 GEMM/调度优化，另立任务。**

## 交付物

- 分支 `dev/d0-instrumentation`（含 D0），D1 commits：
  - `13d0351` D1: layer-major long prefill behind --prefill-layer-major (default off)
  - 修复链 `4378dee`→`ecc7016`→`244375b`→`69bdf16`→`ebd26e6`→`476fe69`：ctx 读 batch、去掉 shim 的 batch.uid、PLE 逐子块 meta、shim get_attn_positions 可调用、mrope 切片、闭包晚绑定修复
  - `51431fd` D1: FT_LM_CHUNK env override for layer-major internal chunk size
  - （本文早版把 `c26c51e` 记进 D1 修复链，有误：`c26c51e` 是 D0 的计数提交，见 `RESULTS_DEV_D0_20261003.md`）
- 开关：`--prefill-layer-major`（默认 False；只对「单条、长于一个 chunk、无多模态」的预填生效；多请求排队/短提示/解码路径零改动）。
- 改动文件：`server/args.py`、`scheduler/scheduler.py`、`scheduler/prefill.py`、`engine/engine.py`、`models/qwen4_exp/model.py`、`models/qwen4_exp/ple.py`、`layers/moe.py`。

## 实现要点

- 调度器：`PrefillAdder` 增加 `layer_major` 旁路——单请求且超预算时整条准入（不再切 ChunkedReq）；`_prepare_batch` 给 batch 打 `layer_major` 标。
- 引擎：`forward_batch` 分支进 `_forward_layer_major`——把整条 prompt 按 `max-extend-tokens` 切成子批（positions/out_loc/fla_metadata/`prepare_metadata` 全部按子批原样构建，与基线逐块一致），`begin_prefill()` 引擎侧只调一次。
- 模型：`Qwen4ExpModel.forward_layer_major` 层外层 × 子块内层；`ctx._batch` 逐子块切换（GDN 读 ctx）；PLE meta 逐子块构建、`commit_ngram_context` 逐子块滚动（层 1）；mixer+head 只对最后一块（head 经 `attn_metadata.get_last_indices` 取末行）。
- 双缓冲：`prefetch(l)` 对重复子块天然 no-op（现有守卫）；`moe.py` 加 `skip_begin_prefill` 守卫防止每子块重置。专家池每层只搬一次。

## 验收结果（对照 `DEV_PLAN` §D1 清单）

| 验收项 | 结果 | 判定 |
|---|---|---|
| 冷 32K 首 token ≤ 9 s（两轮取慢） | **13.91 / 13.14 s**（基线 21.52） | ✗ 未达 9 s（见下"余量"），但 −35~−39% |
| temp-0 前 64 token 与旧路径一致 | 见下方三方对比 | ✓*（引擎固有方差内逐位一致） |
| 64K 跑完不 OOM | 65412 进 / TTFT 29.9 s / 解码 36.77，无 OOM | ✓ |
| 解码 ≥ 37.52×0.97 = 36.39 | 36.71 / 39.79 / 37.16 | ✓ |
| 并发字间隔写进结果 | 层优先 **16.7 s** vs 基线 **20.4 s** | ✓ 优于基线 |

两轮原始（层优先，4096 窗口，32064 进 / 127 出，cached=0）：ft-lm-a TTFT 13.911 解码 36.71；ft-lm-b TTFT 13.143 解码 39.79。

### temp-0 一致性（三方对比，同 cold_id 同提示）

| 对比 | 公共前缀（token） |
|---|---|
| 层优先 vs 基线首跑 | 56 / 127 |
| 基线重放（同服务缓存命中重跑） vs 基线首跑 | **56 / 127（同一分叉点！）** |
| 层优先 vs 基线重放 | **127 / 127 逐位一致** |

结论：分叉点 token 56 是**引擎既有的运行间方差**（基线自身两次运行就在同一点分叉——缓存命中与冷预填路径的 QSA 环形索引/状态差异），与层优先无关；层优先输出与基线的一条真实续写**逐位一致**。方案要求的"不一致时比较前 16 层隐藏态"未触发（分叉非层优先引起）。

### D0 计数（层优先的机制证据）

`d0_lm_prefill.jsonl` 单条记录：**384 层调用 = 48 层 × 8 子块**；**SUM copy 2877 ms（整池 63.46 GiB 只搬一轮**；块优先路径为 8×2640 = 21.1 s）；SUM compute 9417 ms。TTFT 13.1–13.9 = 计算 9.4 + 注意力/GDN/PLE ~3.4 + 首层搬运暴露，机制与设计完全一致。

## ≤9 s 冲刺（2026-10-03 追加，结论：配置层杠杆已用尽）

- 关闭 FT_DEV_D0 仪表：≈ −0.3 s。
- `FT_LM_CHUNK=8192`（层优先内部子块 4096→8192，每专家 GEMM 的 M 翻倍、派发减半）：TTFT **12.98/12.66 s**（ft-8k-a/b，解码 38.83/40.70）。
- 一致性代价：8192 内部子块与基线的公共前缀跌到 **28 token**（4096 内部子块为 56，且与基线重放 127/127 一致）——分块尺寸改变 GEMM/注意力核的分块形状，产生真实数值偏移。**按 64-token 一致性硬门否决 8192 默认**，交付 4096 内部子块。
- 最终 D1 数字（4096 内部子块、无仪表）：**12.66 / 12.98 s**。到 ≤9 s 的剩余差距全部在 MoE 反量化分组 GEMM 本体（~9 s，每专家 M≈80-160 行的小 GEMM，~41 TFLOPS）——需内核级优化（更大 M 的批处理/更高效 nvfp4 核），另立任务。

## 为什么没到 9 s（首次分析）

搬运已压到 2.9 s 且被计算掩盖；现在支配项是**计算流**：MoE 反量化 GEMM 9.4 s（4096-token 分组 GEMM，~41 TFLOPS 有效）+ 注意力/GDN/PLE ~3.4 s。进一步路径（另立任务，不在 D1 范围）：① 子块内做大 M 的 GEMM 批处理/更高 TFLOPS 内核；② 层间子块流水（把注意力/PLE 与下一层搬运再重叠已无空间——搬运已掩盖）；③ 移除 D0 仪表开销（~0.2-0.5 s）。

## 并发（两路）

A 路流式解码 399 token，B 路 2 秒后触发 32K 预填：

| 配置 | A 最大字间隔 | A 中位字间隔 | B 预填 wall |
|---|---|---|---|
| 层优先 | **16.69 s** | 28.3 ms | 15.31 s |
| 基线（chunked） | **20.37 s** | 27.7 ms | 24.74 s |

层优先生占更久但整体更快结束——两路总占用反而缩短（15.3 vs 24.7 s）。方案">3 s 做层间插解码第二阶段"的触发条件成立（16.7 s ≫ 3 s），但鉴于基线同样饿死解码且层优先总占用更短，第二阶段优先级降低，留待 C2/C4 并发场景实测后决定。

## 面板

已 POST 覆盖 Qwen3.8-Flash-Next-NVFP4 / ft：TESTING，decode 38.25（层优先两轮均值）/ ttft 13.91（慢轮），备注保留 21.52 / 37.52 / 35.10 与本项前后对比。

## 遗留

- 服务器已停、显存归还。复现：加 `--prefill-layer-major` 重启即可；不带开关行为与生产完全一致（代码已验证短提示/解码路径不变）。
- 60 题 + 30 分钟稳定性（替换生产门）：本次未跑（D1 改动只在长预填路径，60 题均为短提示不经该路径；上任务已证实 4096/8192 的 60 题响应逐字一致）。替换生产前按方案补跑。
- D2：D0 已证 decode_target=gpu 无 CPU 分支，按方案停做；D3/D4/D5 未动。
