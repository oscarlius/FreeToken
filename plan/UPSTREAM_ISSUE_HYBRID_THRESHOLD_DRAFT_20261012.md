# 上游 issue 草稿（待用户确认后提交到 FlashML-org/FreeToken）

数字与代码位置的核对记录在文末，供审核用，不随 issue 提交。

---

**Title:** bench bw verdict misses in the other direction: auto stays on offload (ratio ~1.9), while hybrid decodes 21% / 55% faster (Qwen3.8-Flash-Next NVFP4, RTX 4090 + dual Xeon)

## Summary

On a dual-socket Xeon + RTX 4090 host, `ft bench bw` measures a CPU-MoE / PCIe-gather bandwidth ratio of 1.90–1.96 for NVFP4 experts (two bench runs). That is just under the default 2.0× threshold, so `--moe-strategy auto` resolves to `offload`. In a same-window A/B test, explicitly selecting `--moe-strategy hybrid` decoded about 21% faster with one stream and about 55% faster per stream with two concurrent streams.

This is one more data point that the bandwidth-ratio verdict does not predict end-to-end decode, here in the opposite direction from #151 and #436 (hybrid picked but slower). It is also related to #278: the served model's experts are about 2.77 MB (H=2560, I=640), whereas the nvfp4 tuning geometry uses 7.97 MB experts.

## Environment

- GPU: 1 × RTX 4090 24 GB, PCIe 4.0 x16 (bench linear H2D: 24.26 GB/s)
- CPU: 2 × Xeon Silver 4310 (24 physical cores in total, AVX-512 VNNI, no AMX), 2 NUMA nodes, 16 × 16 GB DDR4-2666, all channels populated
- Model: Qwen3.8-Flash-Next, NVFP4 checkpoint
- `ft bench bw` profile (nvfp4 tuning geometry, 7.97 MB per expert):
  - latest run: cpu_moe 46.12 GB/s (`avx512f+avx512vnni`, nvfp4-w4a8), pcie_gather 24.25 GB/s → ratio 1.902 → `offload`
  - earlier run: 47.62 / 24.27 GB/s → ratio 1.962 → `offload`
- FreeToken: a fork based on upstream d3512b4, with #577 and #578 cherry-picked plus local instrumentation (disabled in these runs) and OOM-restart patches. The fork does not modify `benchbw.py`, `bench_profile.py` or the CPU MoE executor. I have not re-measured on current main; I see that #610, #619 and #662 have touched the CPU MoE path since.

## Measurement (same window, same build)

Services were started in sequence: offload → hybrid → hybrid (fresh, not warmed) → offload.

- The only differences for hybrid were `--moe-strategy hybrid` and CPU pinning. The fetch fraction was the automatic value (27.7%).
- Prompts were about 1.2K input tokens (two distinct prompts for the two-stream case), with 256 output tokens and temperature 0.
- Each service got two unscored warm-up requests first, except the fresh hybrid service.

| Decode (tok/s) | offload | hybrid |
|---|---|---|
| 1 stream | 29.62–30.19 | 35.55 / 36.59 |
| 2 streams, per stream | 16.81–16.98 | 25.96–26.27 |

- The two offload services differed by 0.20% in two-stream throughput, so the gap is not drift.
- The fresh, unwarmed hybrid service measured 30.81 tok/s single-stream, so most of the single-stream gain appears after warm-up.

## Notes

- With two distinct streams, offload sits close to its PCIe bound at the measured miss rate (about 38%), roughly 23.9 tok/s per stream. Hybrid exceeds that bound because experts computed on the CPU do not cross the link.
- Hybrid is not numerically identical to offload on this CPU, for two reasons:
  - the CPU path quantizes activations to int8 (W4A8);
  - outputs depend on cache history: a fresh and a warmed hybrid service diverged on the same cold request.

  So this is a speed/numerics trade-off, not a free win.

## Questions / suggestions

1. Taken together with #151, #436 and #278, it looks like the bandwidth ratio misses in both directions. Would a short end-to-end decode probe (offload vs. hybrid on the served model, a few dozen steps each) be an acceptable basis for the auto decision, perhaps cached like the bench profile?
2. Short of that: could startup log the measured ratio and the threshold when auto keeps `offload`? Users near the boundary would then know to try `hybrid`. (`ft bench bw --threshold` exists, but a `ft serve` user doesn't see the ratio.)

Caveat: these numbers are from a d3512b4-based fork. Given #436, I'm not assuming hybrid behaves the same on current main, and I'm happy to rerun there or share logs.

---

## 核对记录（op，2026-10-12 晚；不随 issue 提交）

| 项 | 来源 | 结果 |
|---|---|---|
| 阈值与自动选择 | 上游 origin/main 95ac86f：`moe/benchbw.py:617-619` `recommend(..., threshold=2.0)`；`ft bench bw --threshold`（benchbw.py:970）；`engine/engine.py:1668-1752` 只在有缓存 profile 且推荐 hybrid 时升级，否则留在 offload | 前提成立；"阈值可配置"已存在，所以建议 1 改为问它是不是有意留的余量 |
| 比值 | 服务器 `~/.cache/freetoken/benchbw/GPU-052dcdb7….json`（2026-10-11 23:13）：46.12 / 24.25 → 1.902；`plan/HYBRID_ALGORITHM_RESEARCH_20261011.md:94` 记录了更早一次的 47.62 / 24.27 → 1.962 | 原草稿只写了 1.962，现改为 1.90–1.96 |
| A/B 数字 | v5.8 §7.7 同窗口 A/B（runs/dev_hybrid_verify_20261011/window02，候选 481d3a7） | 35.55/36.59 对 29.62–30.19（中点 +20.6%）；25.96–26.27 对 16.81–16.98（中点 +54.6%）；漂移 0.20%；H2 30.81 |
| 基线 | 服务器 git：merge-base(481d3a7, origin/main) = d3512b4；d3512b4..481d3a7 共 61 个提交，含 #578（Yevhenii 4 个）、#577（skavans）；未改动 benchbw.py、bench_profile.py、cpu_executor.py | "fork of d3512b4 + #577/#578" 属实，另加说明本地补丁的性质 |
| 链路上界 | v5.8 §4.7：X 组 m = 38.24%，理想上界 23.87 | 一致 |
| 数值边界 | v5.8 §7.7：W4A8（cpu_moe_ext.cpp quant_i8_pg16），新起服务与预热服务在第 600 字符分叉 | 一致 |
| 去隐私 | 正文没有公司名、主机名、IP 或内部路径（GPU UUID 与主机名 'dell' 都未写入） | 通过 |
| 重复 issue | 用 GitHub 搜索 API（未登录）搜了 benchbw、hybrid threshold、auto strategy、moe-strategy hybrid、bench bw | 没有相同的。相关的有：#151 与 #436（方向相反：自动选了 hybrid，反而更慢；#436 是 Qwen3.8-Flash-Next 在 main 上的 hybrid 回退）；#278 PR（让判定按所服务模型的专家大小来做）；#308、#412（profile 的加载与使用）。正文已交叉引用 |
| 专家大小 | Qwen3.8：路由专家 63.28 GiB ÷（48 × 512）= 2.765 MB；H=2560，I=640 | 写入正文 |

## 对第一篇论文的影响（op 发现，须写进 paper-en/CLAUDE.md）

上游 issue **#579**（YevheniiKotyrlo，2026-09-30，open）已经公开报告：offload 预填时，无论这一段多短，都会把每层全部专家流一遍。Qwen3.8 每段 63.5 GiB，在 PCIe 4.0 x16 上约 2.6 s，长对话的每一轮都要付。这与 v5.8 §7.3 的"每个请求至少一遍、实现地板约 2.8 s"是同一个观察。因此：
- 论文不能把这一点写成首次发现，必须引用 #579；
- 本文的贡献落在三处：按遍数计成本的模型、"一遍 / 两遍"两档的预测与验证、锚点切段的核算。

另外，上游 issue **#29**（TP>1 不支持 Qwen3.5/3.6 MoE）说明，多卡缺口在上游已有人提出。这与第二篇论文的撞车风险有关。
