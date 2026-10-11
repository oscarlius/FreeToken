# 上游 FreeToken 新版本审查：#601（189c8ad）

日期：2026-10-05。审查对象：`FlashML-org/FreeToken` main 自 `d3512b4`（E2-base 的上游基点）之后的全部新提交。
结论：**现在不升级**。对单卡 4090 的生产与测量没有收益，也没有风险；它是卡D13（TP 多卡）将来的有用基座，届时以 ≥ `189c8ad` 为基点。

## 1. 新增内容

`d3512b4..origin/main` 只有一个提交：

- `189c8ad` feat(moe): serve NVFP4 and MXFP4 experts fused through the expert banks (#601)，2026-10-04，20 个文件，+298/−212。
- 标签 `v0.1.2`（08-19）、`v0.1.3`（09-15）都早于 `d3512b4`，不含新内容；`nightly` 仍指向 `d3512b4`。

#601 做了三件事：

1. **常驻（fused）路径支持 NVFP4 / MXFP4 专家**。常驻专家不再走 state dict，改用 offload 的专家库加载器（HF 分片或 FTW 库）直接装进每层 GPU 库（`attach_resident_banks`、`load_ftw_banks_to_device`）。
2. **统一内存 GPU（GB10 / DGX Spark）自动选 fused**，并对 offload 专用参数发警告。
3. **BREAKING**：`ft checkpoint` 总是把 MoE 专家写成库；旧版用 `--moe-backend fused/triton` 转换的 FTW（专家为稠密权重）不能再加载，需要重新转换。

## 2. 对我们的影响（逐项核实）

| 项 | 核实结果 | 影响 |
|---|---|---|
| 硬件 | 服务器 1 × RTX 4090 24 GB，独立显存 | `auto` 仍解析为 offload；统一内存分支不触发 |
| fused 能否用 | NVFP4 专家约 68 GB（P = 68.14 GB）远超 24 GB | 单卡不能常驻，fused 无用 |
| 检查点格式 | 生产模型 `/data2/model/Qwen3.8-Flash-Next-NVFP4` 是 HF safetensors（10 个分片），不是 FTW | BREAKING 改动不影响生产模型。`DeepSeek-V4-Flash-FTW` 的专家本来只能 offload，也不受影响 |
| offload 路径 | `offload_cache.iter_offload_moe_layers` 只是改为复用 `iter_moe_layers`，语义相同；`include_moe_experts` 对 offload 本来就是 False；NVFP4 内核只删了「不允许常驻」的拒绝条件，offload 计算不变 | 预期默认路径逐位不变（未实测） |
| 与 E2-base 合并 | 在临时 worktree 中把 E2-base 全部补丁（`d3512b4..23f2e2c`，不含 `.bak`）叠到 `189c8ad` 上：`git apply --3way` 返回 0，无冲突标记，4 个重叠文件（`engine.py`、`layers/moe.py`、`offload_cache.py`、`server/args.py`）语法检查通过 | 文本可以干净合入 |
| 语义交集 | 我们在 `layers/moe.py` 的 7 处改动都在 `OffloadMoELayer` 内（D0 计时，读 `self.layer_id`）；`engine.py` 的 6 处在 D0、预填区域。#601 改的是权重加载与 `_adjust_config` | 无语义交集 |

## 3. 为什么现在不升级

1. **没有收益**：单卡 4090 上 #601 不改变任何执行路径。
2. **有成本**：换上游基点就是换代码版本（`00_规则` §9），E2-base / E2-base.1 的全部基线数字（T00、E2-R009、T16 门等）都要在新基点上重做，P0 主线（卡D14 → 卡D16 → 卡D17 → T20）会被打断。
3. **E2-R032 与 T19 正在运行**，此时换基点会造成版本混淆。

## 4. 对多卡 TP 方案（卡D13）的意义

用户决定多卡沿用 TP。TP4（4 × 24 GB）让专家常驻、消除卸载，需要两块：

| 需要 | #601 之后的状态 |
|---|---|
| NVFP4 专家常驻加载 | **已有**（#601 的专家库直装 GPU） |
| NVFP4 专家内核支持 TP > 1 | **仍没有**：Triton、Marlin、b12x 三个 NVFP4 内核都是 `tp_ok=False` |
| 模型权重加载支持 TP > 1 | **仍没有**：`qwen4_exp/weight.py:206` 只支持 TP=1 |

所以 #601 替卡D13 完成了「常驻加载」这一块，「TP 切分」两块仍要自己做。卡D13 启动时应以 ≥ `189c8ad` 为基点，开新一代（E3），不要把 TP 移植到 `d3512b4` 上。

## 5. 建议动作

- 不改生产，不改 E2-base / E2-base.1，不打断当前队列。
- T13（上游 PR 跟踪）登记 #601：已审，暂不合入；卡D13 启动时的基点候选。
- 下次换代（卡D13 启动，或上游出现与 offload / 预填 / radix 续算相关的修复）时一并合入，届时按 T16 门验证默认路径逐位不变。
- 若以后要用 FTW 加载：只能用 #601 之后的 `ft checkpoint` 重新转换，旧 FTW 不能混用。

## 6. 证据

- 本地：`freetoken/upstream-flashml`，`git fetch` 后 `origin/main = 189c8ad`；本地 `main` 未动（仍为 `d3512b4`）。
- 服务器（只读）：`nvidia-smi`、`ls /data2/model/Qwen3.8-Flash-Next-NVFP4`、`git -C /data2/FreeToken/wt/e2base diff --stat d3512b4 HEAD`。
- 合并演练：临时 worktree 在 scratchpad 中创建，演练后已删除。
