# 论文目录

## 当前版本

| 项 | 值 |
|---|---|
| 版本 | **v4.0**（2026-10-03，第一阶段定稿） |
| 标题 | 共享资源约束下主存卸载 MoE 的多 GPU 低延迟协同执行——以专家流遍数与 PCIe 时间预算为调度成本单位 |
| 作者 | 刘尚锋 |
| 正文 | [`FreeToken_MultiGPU_CoExec_v4.0.html`](FreeToken_MultiGPU_CoExec_v4.0.html)（单文件 HTML，arXiv 预印本排版，含 9 幅图、12 张表） |
| 数据版本 | FTD-20261003-1（清单见 `../plan/data_releases/`，规则见 `../plan/00_规则_测试存储与数据版本.md`） |
| 证据边界 | 单卡为实测；多卡为推导与方案，没有多卡实测；新调度机制的净收益尚待 E1-R008、E1-R005、E1-R007 等对照 |

## 怎么改

- 正文在 `src/body_v4.html`，配图在 `src/figures.py`（坐标由数据计算），排版与组装在 `src/build_v4.py`。
- 修改后运行 `python paper/src/build_v4.py` 重新生成 HTML，不要直接改生成的 HTML。
- 数字只引用已发布的数据版本。新数据进入新的 FTD 发布后：
  - 新增数据：次版本号 +0.1（v4.1，文件名同步改）。
  - 结论性变化：主版本号 +1。
  - 旧版 HTML 移入 `archive/`。
- 署名：原论文作者（UC Berkeley 等）与上游 PR 贡献者（Yevhenii，#578；skavans，#577）列在「致谢」，没有列为作者。如果他们同意署名，需要书面确认后再改作者栏。

## 版本历史

| 版本 | 日期 | 文件 | 要点 |
|---|---|---|---|
| v4.0 | 10-03 | `FreeToken_MultiGPU_CoExec_v4.0.html` | 主题改为多 GPU 协同执行；新增多卡字节守恒、主存预算、组级执行器、原理图；arXiv 排版 |
| v3.2 | 10-03 | `archive/freetoken-4090-agents_v3.2.md` | 开关四格重读；状态层等价；回复 Grok 与 GPT-6 的合并审阅 |
| v3.1 | 10-03 | `archive/freetoken-4090-agents_v3.1.md` | 回复 GPT-6 对 v3 的审阅：条件上界、重叠模型、D14 |
| v3 | 10-03 | `archive/freetoken-4090-agents_v3.md` | 首个终稿：遍数后果、PCIe 预算、排队 |
| v2 / v1 | 10-03 | `archive/` | 早期草稿；GPT-6（Astro）方向稿与协议稿也在 `archive/` |

外部审阅意见在 `openai/` 与 `archive/openai opp/`。其中 `openai/README.md` 与 v3.2 逐字节相同，不含新增意见。我们的逐条回复在 `../research/REPLY_*.md`。
