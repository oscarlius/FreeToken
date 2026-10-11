# 调研任务：FreeToken 上游里专家、DSA、路由表各走哪条路

只读。不要改 `upstream-flashml` 里的代码，不要在 172.16.108.9 上启动或重启 8095，不要下载模型。

## 仓库

- 路径：`freetoken/upstream-flashml`
- 远程：https://github.com/FlashML-org/FreeToken
- 提交：`d3512b43affe981465e03ee28cbd88f49c39b9aa`（2026-10-01，`fix(ple): fence disk staging against in-flight lookups`）
- 论文：https://arxiv.org/html/2608.16157v1
- 包代码在 `upstream-flashml/python/freetoken/`

本机对照（只作背景，本次不要上机测）：1×RTX 4090 24GB、双路 Xeon Silver 4310、251GiB、GPU 在 NUMA 1、服务核 `1,3-23`。目标模型只有 Qwen3.8-Flash-Next 与 GLM-5.3-Flash。

## 要回答的问题

论文把显存缓存的单位写成完整的 `(层, 专家)`，解码未命中按 \(q^\star \approx m \cdot B_P / B_H\) 分成「搬上 GPU」和「CPU 上算」。DSA 和路由表不是这种专家。请用文件和行号说明上游代码实际怎么放它们。

1. 专家卸载。`python/freetoken/moe/offload_kernels.py`、`cpu_executor.py`、`benchbw.py` 里，fetch fraction 是否就是论文的 \(q^\star\)？预填是整层双缓冲，还是按需搬？什么条件下退回按需？有没有张量并行或把一个专家切到多张卡的代码？
2. DSA。从 `tests/models/test_glm_dsa.py` 追到实现。GLM 的 DSA（indexer、sparse top-k、latent KV）权重在 GPU、CPU 还是磁盘？解码时会不会进入专家槽？Qwen 的稀疏注意力 / QSA（`tests/models/qwen4_exp/test_qsa_kernels.py` 一带）是不是另一套，和 GLM DSA 有没有共用缓存？
3. 路由表。分开写三类，不要混成一个「路由」：
   - MoE gate：体积小，应常驻 GPU。代码是否如此？
   - Qwen PLE / n-gram 表：`tests/models/qwen4_exp/test_ple_disk.py`、`GpuResidentTable`、提交说明里的 disk staging。表是整表进显存、热行缓存，还是按 token 从磁盘取行？取行和专家预填是否抢同一条 PCIe？磁盘读进行中，查找如何被挡住（fence）？
   - Engram 或 GLM 侧同类大表：有没有与 PLE 不同的路径？
4. 循环状态。Gated DeltaNet / KDA（`test_glm5_next_kda_*.py`）的状态检查点是否按论文放在工具调用、thinking 这些特殊 token 边界？和 DSA 的 KV 是不是同一个池？
5. 和论文不一致的地方。列出「论文有、这份代码没有」和「代码有、论文没写」的行为。每条都要文件和行号。没有行号的判断标成未证实。

## 交付

用中文写一份只读结论，结构固定为：

- 已实现（文件:行号）
- 代码里没有
- 还不能确定
- 对本机的含义：专家的 \(q^\star\)、DSA、PLE/路由表，这三件事里哪一件会改预填搬运量，哪一件会改解码带宽。不要给新的量化方案，不要建议张量并行。

把结论交回当前对话，不要改服务配置。
