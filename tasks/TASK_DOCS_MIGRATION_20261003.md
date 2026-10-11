# 任务书：freetoken/ 文档按类型迁移（2026-10-03）

> 类别：任务书。执行方：开发 agent（需要正常可用的本地 shell）。
> 依据：`freetoken/INDEX.md` 第 1 节（目录约定）和第 3 节（新旧路径对照）。
> 时机：等你手上 E1-R003 的写入告一段落再做，避免一边迁移一边往旧路径写 `RESULTS_E1_20261003.md`。

## 1. 要做的事

1. **移动文件**：按 `INDEX.md` 第 3 节的对照表，把 17 份文档移到 `plans/`、`tasks/`、`results/`、`research/`。工作区是 git 仓库就用 `git mv`，否则用 `Move-Item`。`reports/`、`tasks/` 两个目录已经存在，里面的新文件不要动。
2. **改文档之间的引用**：在 `freetoken/`、`_shared/` 下的 `.md`，以及 `modelscope/README.md` 里，查找每个被移动文件的文件名，改成新路径。
   - 同目录内的引用写文件名即可。
   - 跨目录的引用写成从工作区根开始的路径，例如 `freetoken/results/RESULTS_DEV_D1_20261003.md`。
3. **改面板数据里的「来源」文字**：
   - 服务端数据：`devrun.json`（39 处）、`rounds.json`（10 处）、`research.json`（1 处）。走面板接口改，不要直接改容器里的文件。
   - 本地文件：`_shared/model_hub_dashboard/rounds_seed_E0.json`（10 处）、`TASK_DEVRUN_DASHBOARD_20261003.md`（14 处）。
   - 规则：`freetoken/<文件名>` 改成 `freetoken/<子目录>/<文件名>`。
4. **改 `freetoken/README.md`**：
   - 标题下加一行：「文档总目录和分类约定见 `INDEX.md`；新文档按类型直接放进 `plans/`、`tasks/`、`results/`、`reports/`、`research/`、`paper/`，待测队列也在那里。」
   - 「结果归档」一节里的文件名改成新路径。
5. **改工作区根目录的 `AGENTS.md`**：在「📌 FreeToken (FT)」的隔离要求里，紧接在「FreeToken 的 Python 运行环境为 `/data2/FreeToken/venv`。」这一行之后，加一条：

   > `freetoken/` 下的文档按类型放进子目录：`plans/`（方案）、`tasks/`（任务书）、`results/`（测试结果）、`reports/`（解读与验收）、`research/`（依据：调研与评审）、`paper/`（论文）；脚本放 `scripts/`。**不要在 `freetoken/` 根目录新建文档**（只保留 `README.md` 和 `INDEX.md`）。文档状态和待测队列记在 `freetoken/INDEX.md`，新增文档或状态变化时同步更新。

6. **更新 `INDEX.md`**：第 3 节标题改为「旧文档迁移对照（已于 YYYY-MM-DD 执行）」；第 2 节里 `PROJECTION_PERF_PLAN` 的说明路径改为 `plans/`。
7. **脚本和代码注释**（可选）：`scripts/agent_trace.py`、`scripts/probe_ft_cold32k.py`、`_shared/probe_cold32k.py`、`_shared/dev_d0/` 下的注释里也有旧文件名。顺手改掉即可；不改也不影响运行。

## 2. 不要动的东西

- `upstream-flashml/` 整个目录。
- `paper/freetoken-4090-agents.md`：论文引用的是轮次库路径，不是文档路径，迁移不影响论文。
- `_shared/PAPER_COMPARE_KT_FT_20261003.md`：跨框架文档，留在 `_shared/`。

## 3. 验收

| # | 检查 | 通过条件 |
|---|---|---|
| 1 | `freetoken/` 根目录的 `.md` | 只剩 `README.md` 和 `INDEX.md` |
| 2 | 旧路径残留 | 在 `freetoken/`、`_shared/`、`modelscope/` 的 `.md` 和 `.json` 里，搜索 `freetoken/` 后紧跟 `RESULTS_`、`TASK_`、`TEST_TASK_`、`DEV_`、`RESEARCH_`、`REVIEW_`、`PROJECTION_` 的写法，结果为 0（`upstream-flashml/` 除外） |
| 3 | 面板 | `/api/devrun`、`/api/rounds`、`/api/research` 里的来源文字都是新路径；8098 首页返回 200。论文页已删除，不要求 `paper.html` |
| 4 | `AGENTS.md` | 新增的那条规则在 FreeToken 一节里 |
| 5 | 文件数 | 迁移前后 `.md` 总数一致，没有丢文件 |

完成后在 `INDEX.md` 第 3 节标注执行日期，并回报验收表的结果。
