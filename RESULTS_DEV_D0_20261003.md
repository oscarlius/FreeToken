# D0 交付：计时与计数埋点（2026-10-03）

方案：`DEV_PLAN_FT_QWEN38_20261003.md` §D0。只加仪表、不改行为；环境变量 `FT_DEV_D0=1` 打开（默认关），输出路径 `FT_DEV_D0_PATH`（默认 `/tmp/ft_dev_d0`）。

## 交付物

- 分支 `dev/d0-instrumentation`，commit：
  - `c26c51e` D0: env-gated prefill byte/timing counters + decode stats dump (FT_DEV_D0)
  - `76a0d74` D0: guard decode-stats dumper against CUDA graph capture
  - （后续两个 fix commit：enable_timing、flush 时统一解析 elapsed、每层新建事件）
  改动文件：`python/freetoken/moe/offload_cache.py`（+150 行左右）、`python/freetoken/engine/engine.py`（collect_stats 接 D0 开关，2 行）。
- 开关名：`FT_DEV_D0`（1=开）；`FT_DEV_D0_PATH=<base>`（写 `<base>_prefill.jsonl` 每块一行 + `<base>_decode.json` 解码统计周期快照）。
- 默认关闭：✓（未设 env 时零行为差异，已验证正常启动）。

## 埋点内容

1. **预填**：`begin_prefill` 按块冲刷 JSONL：每层 `{layer, copy_ms(H2D 拷贝流), compute_ms(计算流), d2d_ms(hit 显存内拷贝)}` + 块合计 `{h2d_bytes, d2d_bytes, wall_s}`，服务日志同步打一行摘要。实现点：`_prefetch_split`/整层回退路径计字节（小 bank 整层 H2D、大 bank hit/miss 分拆）+ CUDA 事件；`wait/release_prefill_layer` 计算流事件；elapsed 在下一块 begin_prefill 的 flush 统一解析（flush 前 `torch.cuda.synchronize`，规避 host 领先 GPU 的 elapsed 竞态）。
2. **解码**：2 秒周期 dump `decode_miss_stats()` + `decode_miss_stats_per_layer()`（m、q、CPU 执行数、失误率）到 `<base>_decode.json`。CUDA graph 捕获期间自动暂停读取（防 capture 作废）。
3. **CPU 专家核 NUMA 统计**：**N/A**——生产配置（`--moe-strategy offload`）自动解析为 `decode_target='gpu'`，解码无 CPU 分支（`cpu_executor=None`，D0 解码输出 `fetch_rate=0`/CPU 计数 0 证实），`cpu_moe_ext.cpp` 在此路径不执行；C++ 埋点待 D2/混合目标启用时再补。

## 验收结果（冷 32K，ft-d0-d/e 两轮，32064 进 / 128 出，cached=0）

| 块内合计 | 实测（两轮一致） |
|---|---|
| H2D 字节 | **58.59 GiB/块** |
| hit-D2D 字节 | **4.86 GiB/块（命中仅 7.7%）** |
| 每层 copy 耗时 | ~55 ms（48 层 **SUM copy ≈ 2640 ms/块**） |
| 每层 compute 耗时 | ~25 ms（48 层 **SUM compute ≈ 1213 ms/块**，完全被搬运掩盖） |
| 块 wall | 2.68 s × 8 块 ≈ TTFT 23.1 / 21.6 s ✓ |

**D1 前提判定：成立。** 每块 H2D ≈ 整个专家池（63.46 GiB，实际测得 58.59+4.86=63.46），8 块合计 ≈ 8×整池 ≈ 507 GiB，不是"命中率高"的反例。搬运是预填的支配项（copy 2.64s ≫ compute 1.21s）。

## 对 D1 点估计的改写（按方案第 4 节公式）

- 搬运：整条请求一轮 = 63.46 GiB ÷ 24.3 GB/s ≈ **2.7 s**（首层暴露 ~0.06 s）。
- 计算：块状 GEMM 实测 8 × 1.21 s ≈ **9.7 s**；层优先把每层 GEMM 的 token 数从 4096 提到 32064，反量化 GEMM 效率通常提升 1.5–2×，总计算估 5–6.5 s。
- **TTFT(D1) ≈ max(搬运 2.7 s, 计算 5–6.5 s) + PLE/其他 ≈ 6–8 s**（方案点估计 6 s，区间 4.5–9 s 的后段；以实测为准）。
- 64K：计算翻倍 ≈ 12–14 s，激活 1.4 GB 需按子块组退化。

## 调试记录（复现要点）

- CUDA graph 捕获期间任何设备同步读取都会作废捕获 → dump 线程必须带捕获守卫（`torch.cuda.graph.__enter__/__exit__` 计数）。
- `torch.cuda.Event()` 默认 `enable_timing=False`，elapsed 需显式开。
- 双缓冲复用事件对象会覆盖 GPU 时间戳（SUM compute 出现负值）→ 每层新建事件。
- host 领先 GPU 时 `elapsed_time` 抛 "Both events must be completed" → 解析推迟到块边界 flush（先 synchronize）。
