# 任务：补轮次字段并把论文第 2 版导入 8098（2026-10-03）

> **已取消（同日）。** 用户决定删掉 8098 的论文编辑器，论文由 Agent 在本地 `paper/freetoken-4090-agents_v2_draft.md` 修改。不要执行下面的导入。
>
> 类别：任务书。执行者：开发 agent（面板 / 论文编辑器）。
> 依据：`research/REVIEW_GPT6_DIRECTION_20261003.md`（用户已同意：单卡核心问题改为 H0，论文按模块表重排）；`reports/REPORT_E1_20261003.md` 第 5、6 节。
> 草稿：`freetoken/paper/freetoken-4090-agents_v2_draft.md`。

## 背景

线上论文 `freetoken-4090-agents` 现在是版本 1（design-agent 导入，40 处引用全部可解析）。第 2 版草稿引用了一批轮次库里还没有的字段，必须先补字段，校验器通过后再导入，否则页面会显示红色「缺数据」。

## 约束

- 论文写入口令只在容器内由 `import_paper.py` 读取，不出现在命令行、日志或回复里。
- 不改草稿正文。如果某个字段路径必须换名，回报给设计，由设计改草稿。
- 写轮次只用 `POST /api/rounds/record`（合并）和 `POST /api/rounds/verdict`；只补字段，**不覆盖已有的 `results` 和 `verdict`**（下面明确要改判定的两项除外）。
- 已有的键全部保留，包括名字不准确的 `E1-R002.cold32k_4096_matched`（实际是 8192 分块），因为论文在引用。
- 下表的「参考值」是设计从报告里取的数字，用来核对。**入库的值以原始工件为准**；和参考值相差超过 2% 时，用工件的值，并在回报里列出差异。

## 第 1 步：开工前检查

`GET /api/papers/freetoken-4090-agents` 的 `version` 必须仍是 1。如果不是，说明用户在编辑器里改过，停下来回报，不要导入。

## 第 2 步：补轮次字段

### E1-R001（新字段和推算）

| 路径 | 参考值 | 来源 |
|---|---|---|
| `results.d0.moe_compute_s` | 2.22（层优先冷 32K 一条请求的 MoE 计算合计；两枪就写数组） | `E1-R001/`、`E1-R001b/` 的 D0 |
| `results.d0.parent_moe_compute_s` | 9.42（E1-R000b 同口径） | `E1-R000b/` 的 D0 |
| `results.d0.copy_per_pass_s` | 2.86 | 同上 |
| `results.d0.non_moe_s` | 每枪「首 token − MoE 计算」，约 4.2 | 同上 |
| `results.ctx64k.moe_compute_s` | 4.34 | `E1-R001-64k/`，以及被误追加到 `E1-R003/d0_prefill.jsonl` 末尾的 4 条（报告第 6 节第 4 项） |
| `results.ctx64k.non_moe_s` | 每枪，约 8.1–9.7 | 同上 |
| `projection["cold32k_layer_major.ttft_s"]` | [6.5, 7.7, 9.7] | 计划文档 §4.1 |
| `projection["ctx64k.ttft_s"]` | [17.1, 19.4, 23.5] | 计划文档 §4.1 |

### E1-R003（回放结果，判定改为 not_met）

| 路径 | 参考值 | 来源 |
|---|---|---|
| `results.replay_warm.prompt_tokens` | 按轮次顺序的数组，含第 0 轮 | `E1-R003/` 的回放 JSON |
| `results.replay_warm.recompute_tokens` | 第 1–11 轮：64, 60, 52, 45, 48, 633, 909, 663, 529, 62, 108 | 同上 |
| `results.replay_warm.turn_ttft_s` | 第 1–11 轮：2.66, 2.66, 2.66, 2.66, 3.50, 5.31, 5.31, 2.69, 5.31, 2.68, 2.68 | 同上 |
| `results.replay_warm.ttft_mean_s` | 3.46（第 1–11 轮的均值，不含第 0 轮） | 同上 |
| `results.replay_warm.ttft_max_s` | 5.31 | 同上 |
| `results.replay_cold.recompute_tokens` | 第 1–11 轮：256, 124, 372, 237, 176, 633, 909, 663, 529, 62, 108 | 同上 |
| `results.replay_cold.turn_ttft_s` | 第 1–11 轮：2.61, 2.61, 5.22, 5.19, 5.19, 5.21, 5.21, 2.62, 5.21, 2.63, 2.62 | 同上 |
| `results.d0.h2d_gib_per_segment` | [57.7, 63.5]（各预填段 H2D 的最小值和最大值） | `E1-R003/d0_prefill.jsonl`（去掉末尾 4 条 64K 记录） |
| `verdict` | `not_met`，备注：确定性门未过（第 0、2、3 轮热冷前 32 token 不一致）；编辑类门未测 | `E1-R003/verdict.json` |

数组都包含第 0 轮时，在 `results.replay_warm.note_turn0` 写明第 0 轮是否计入均值。

### E1-R002（只改判定）

- `verdict` 改为 `rejected`，备注：「否决的是当前 CPU 执行器加当前绑核方式（线程绑 0..22 号核，与占用 0、2 号核的常驻进程冲突）；hybrid 本身待 E1-R002b 复测」。

### E1-R005（更新推算）

第 0 代的停顿推算已经过时，换成第 1 代的：

| 路径 | 新值 |
|---|---|
| `projection["stall_cold_prefill.other_max_gap_s"]` | [6.1, 6.4, 6.6] |
| `projection["stall_turn_prefill.other_max_gap_s"]` | [2.6, 2.7, 5.3] |

### E1-R008（新建轮次）

| 字段 | 值 |
|---|---|
| `round_id` | `E1-R008` |
| `epoch` | 1 |
| `title` | 锚封顶开关 A/B（D12 第一步：每轮只搬一遍） |
| `parent` | `E1-R001` |
| `verdict` | `planned` |
| `projection["agent12.turn_ttft_mean_s"]` | [2.6, 2.75, 2.9] |
| `projection["agent12.turn_ttft_max_s"]` | [2.6, 2.7, 2.9] |
| `projection["agent12.two_segment_turns"]` | [0, 0, 0] |

报告第 6 节的其余几项数据修正（第 2–6 项）可以同一次做；第 2 版只依赖上面这些。

## 第 3 步：校验

```
python3 check_paper_refs.py freetoken/paper/freetoken-4090-agents_v2_draft.md
```

退出码必须为 0，缺数据为 0。另外跑一次 `--selftest`，确认校验器本身没有失效。

## 第 4 步：导入为版本 2

用 `import_paper.py` 导入，参数：`base_version=1`，`author=design-agent`，`message="v2: H0 遍数成本 + 第 1 代数据 + 模块表重排"`。如果 `import_paper.py` 不支持指定文件或 `base_version`，扩展它，不要绕过口令机制。

## 第 5 步：验收

| 检查 | 通过条件 |
|---|---|
| 版本 | `GET /api/papers/freetoken-4090-agents` 的 `version` = 2；版本列表里 v1 仍在 |
| 引用 | `preview_refs` 全部 `ok: true`，回报总数 |
| 导出 | `export?resolve=0` 和 `export?resolve=1` 都返回 200 |
| 页面 | `paper.html?id=freetoken-4090-agents` 能打开；附录 A 的第 1 代表格有内容 |
| 判定标签 | E1-R002 显示 rejected，E1-R003 显示 not_met，E1-R008 显示 planned |

## 回报内容

1. 引用总数和缺数据数。
2. 和参考值相差超过 2% 的字段，列出工件值、参考值和工件路径。
3. 第 0 轮是否计入均值。
4. 新版本的 sha256。
