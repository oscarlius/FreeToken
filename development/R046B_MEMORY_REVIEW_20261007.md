# R046b 独立输入窗口与 trace 布局复核

结论：**BLOCKED_INPUT_WINDOW**。实际 `seed_real` 首条请求为 **87,100 token**，超过固定 `--max-seq-len-override 49152`；不能签署 `.80` 预算或 GPU 启动复核。

证据时间：服务器真实 `2026-10-07 10:00:14 CST`。本轮只执行 CPU 前端与必要读取，未发 HTTP、创建 GPU 上下文、获取锁、创建正式轮次或复读已封存原始 tensor / JSONL。

## 实际输入

使用正式服务模型路径 `/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay`，候选 `/data2/FreeToken/wt/e2base1-p1` 的真实 `TokenizeManager.render_prompt` 与 `TokenizeManager.tokenize`，执行原客户端 `build_payload`。三种 seed 均按 `seed + "\n\n" + TASK_PROMPT` 构造，保留三个工具、thinking 默认开启、12 请求及每请求 2048 completion token。

| 输入 | seed 自身 token | 实际首条完整提示 token | 说明 |
|---|---:|---:|---|
| G3-off / G3-on cold | — | 32,064 | 已封存 small review 的原协议元数据；没有复读冷原始结果 |
| G4 Agent trace | — | 659 | 两请求，后续提示依赖现场生成及工具输出 |
| G_seed12k | 12,000 | 12,660 | raw SHA 与正式工装登记一致 |
| G_seed_45k | 11,774 | 12,434 | 文件名不代表实际 token 数；raw SHA 与登记一致 |
| G_seed_real | 86,441 | **87,100** | 首条已经超窗；raw SHA 与登记一致 |
| G_two left / right | — | 8,000 / 8,000 | 原 `make_messages` 生成不同内容；每请求 256、两路合计 512 completion 预算 |

`scheduler.py:614-638` 计算 `max_output_len = max_seq_len - input_len`，小于等于零即返回 `context_length_exceeded`。完整保留每请求 2048 completion 预算还要求输入不超过 47,104 token。未来生成的多轮 messages 尚未冻结，不能把已测首条 token 数称为12轮全部提示的精确上界。成功准入的提示最多49,151 token，但该窗口不能自动截断超长真实输入。

## Trace 缓冲的源码事实

`route_trace.py:92-106` 的原始路由快照目的地为 **CPU pinned `[T,10] int16`**；48个 MoE 层每forward的主机快照数据为 `48 × T × 10 × 2` 字节。32,064 token 对应 **30,781,440 B**，不是628 MiB的 GPU route buffer。

`engine.py:1051-1060` 在 trace 打开时放弃 `forward_layer_major`，转为整提示 eager `model.forward`。调度器仍因 `prefill-layer-major` 将长提示整体准入，因此 `max-prefill-length=4096` 此时不能当作实际 eager 张量长度上界。

真实模型 text config 为 `hidden=2560`、`hc_count=4`、key heads16、value heads48、key/value dim128、bf16。`qwen4_exp/gdn.py:49-51,95-103` 的 contiguous 张量形状为 `[10240,T]`，元素2 B：

- 32,064 token：**656,670,720 B = 626.25 MiB**，与历史628 MiB的分配量级吻合。
- 49,152 token：1,006,632,960 B。
- 已测实际首条87,100 token：1,783,808,000 B；该请求首先会被窗口门拒绝。

`kernel/causal_conv1d.py:38-48` 的卷积在此张量上原位执行并返回同一 `x`；不能再把同shape输出算一份。上述源码说明不得把628 MiB直接当GPU路由数据，再与 eager 临时张量重复相加。完整 eager 峰值还包括其他存活张量，单个 contiguous 大小不能证明1.5 GiB余量。

## 显存依据的边界

只读既有 R055b 独立 small review，未重读其旧 memory JSONL。该 review 的 `failed_harness` 不变：`min_free=1,144,717,312 B`、`total=25,250,627,584 B`、`model_loaded_free=2,681,929,728 B`。旧两轮OOM为申请628 MiB、剩余625.69 MiB；剩余625.69 MiB不是缺口，也不是可直接分离的纯trace数据成本。

输入已经违反固定窗口，故本轮不伪造 longest-prompt `.80` 余量通过值。JSON 中 `estimated_route_overhead_bytes`、`predicted_free_bytes` 为 null，`memory_margin_verified=false`。原输入构造协议需用户裁定；本轮未截断 seed、扩大 KV、改源或签署启动。

## 可审查工件

- 远端报告：`/data2/FreeToken/runs/dev_R046/r046b_memory_budget_v1.json`，0444；SHA256 `71dfde4f5ae90aa8c0f3c3beb3635b20933af1a18a5af2ab0a6e6e323ea4be6b`。
- CPU执行回执：`/data2/FreeToken/runs/dev_R046/r046b_memory_budget_v1.execution_receipt.json`，0444；SHA256 `c758e0d29fc3ee15fefbd32ec1a480438f497b4aaf68b5e444878c1987bf32e5`。
- 本地副本：本目录 `r046b_memory_budget_v1.json` 与 `r046b_memory_budget_v1.execution_receipt.json`，已核 SHA 一致。

报告绑定实际 UID1000/dell、cwd `/data2/FreeToken`、FT venv、CUDA隐藏、socket guard源码SHA及deny函数身份、模型overlay与真实tokenizer/template/config SHA、前端与客户端源码SHA、每条实际payload/messages/rendered prompt/token IDs SHA。没有把环境诊断或工装执行通过当作GPU准入。
