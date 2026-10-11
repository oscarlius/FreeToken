# FreeToken 工程文档索引

> 本文件是 `freetoken/` 下所有文档的总目录：每份文档属于哪一类、放在哪里、现在是什么状态。
> 新文档**直接建在对应的子目录里**；旧文档按第 3 节的对照表迁移（尚未执行，原因见第 3 节）。
> 线上数据不在本目录：轮次库在 8098 `/api/rounds`，原始工件在服务器 `/data2/_shared/runs/ft_rounds/<轮次>/`。论文不在 8098，由 Agent 直接改 `paper/` 里的文件。

---

## 1. 目录约定

| 目录 | 类别 | 放什么 | 谁写 |
|---|---|---|---|
| `plans/` | 方案 | 为什么做、做什么、推算和路线图 | 设计 |
| `tasks/` | 任务书 | 交给执行 agent 的开发或测试任务，含步骤、门槛和预期 | 设计 |
| `results/` | 历史测试结果（停止新增） | 仅保留既有 `RESULTS_*.md` 记录；自 2026-10-03 起不再新增 | — |
| `reports/` | 解读与验收 | 对结果的分析、和推算的对照、验收结论 | 设计 |
| `research/` | 依据 | 调研、上游代码阅读、外部方案评审 | 设计或调研 agent |
| `paper/` | 论文 | Agent 直接编辑的论文正文。不上传到 8098 | 设计 |
| `scripts/` | 脚本 | 启动、探针、回放、分析脚本 | 执行 agent |
| `upstream-flashml/` | 上游源码 | 上游仓库副本，不放我们的文档 | — |

**编号与结果入口。** 根目录 `results/` 表中的 `RESULTS_DEV_D0/D1/D3_*.md` 属于旧 `D0`–`D5` 方案命名空间；其中 `D2`、`D4`、`D5` 为冻结历史条目，未被省略。当前计划卡使用 `plan/02_开发任务/` 的 `D00`–`D14`，机制代码另行标注，不能按数字等同；D0–D9 的逐项对照见 [`plan/README.md`](plan/README.md#编号命名空间与结果存储)。自 2026-10-03 起，`RESULTS_DEV_*` 与根目录 `results/` 停止新增。新卡的本地文字结果位置和内容限制以 [`plan/00_规则_测试存储与数据版本.md` 第 4 节](plan/00_规则_测试存储与数据版本.md#4-本地文字结果)为准：`plan/01_测试与调研/results/`；根目录历史结果仅保留为指针。

**状态不单独建目录。** 一份任务书会从「待测」变成「完成」，如果按状态分目录，每次状态变化都要搬文件，链接也会跟着断。所以目录只按文档类型分，状态记在下面第 2 节的表里；当前要测的内容单独列在第 4 节。

命名沿用现有习惯：`类型前缀_主题_日期.md`，例如 `RESULTS_E1_20261003.md`、`REPORT_E1_20261003.md`。

---

## 2. 文档总表

### 方案（`plans/`）

| 文档 | 状态 | 说明 |
|---|---|---|
| `plans/DEPLOY_OFFICE_WSL2_20261006.md` | 待执行 | 办公机（3090 涡轮 24GB/64GB）WSL2 部署 FreeToken 的清单：环境对齐（torch 2.11+cu130）、PLE 47.7GB 锁页在 WSL2 的配置、模型落位、冒烟与验收对照表 |
| `PROJECTION_PERF_PLAN_20261003.md` | 现行，部分过时 | 性能推算和第 1–4 阶段计划。§3.1、§4.1、§4.4、§4.8 以 `reports/REPORT_E1_20261003.md` 为准 |
| `DEV_PLAN_FT_QWEN38_20261003.md` | 历史 | 早期开发方案（旧 `D0`–`D5` 命名；新结果存储见 `plan/00_规则_测试存储与数据版本.md` 第 4 节） |
| `DEV_NEXT_FT_QWEN38_20261003.md` | 历史 | 早期下一步方案 |
| `DEV_NEXT_D3_20261003.md` | 被 E1-R003 取代 | D3 多锚检查点方案；后续改为基于 #577 |

### 任务书（`tasks/`）

| 文档 | 状态 | 对应结果 |
|---|---|---|
| `TASK_DOCS_MIGRATION_20261003.md`（已在 `tasks/`） | 待办 | 本文件第 3 节的迁移，加上 `README.md` 和 `AGENTS.md` 的规则更新 |
| `TASK_PAPER_V2_IMPORT_20261003.md`（已在 `tasks/`） | 取消 | 用户决定论文不上传 8098。轮次字段补录如果还要做，另开任务，不随论文导入 |
| `TASK_G0_TP_MEMORY_20261003.md`（已在 `tasks/`） | 待办 | 结果写入 `results/RESULTS_G0_TP_MEMORY_20261003.md`；决定四卡怎么组 |
| `TASK_UPSTREAM_PRS_HYBRID_20261003.md` | 进行中 | E1-R001 完成（kept）；E1-R002 完成，待复测；E1-R003 运行期部分进行中 |
| `TASK_FT_PAPER_HEADROOM_20261003.md` | 完成 | `RESULTS_FT_PAPER_HEADROOM_20261003.md` |
| `TEST_TASK_FT_COLD32K_TTFT_20261002.md` | 完成 | `RESULTS_FT_COLD32K_20261002.md` |
| `RESEARCH_TASK_UPSTREAM_DSA.md` | 完成 | `RESEARCH_REPORT_UPSTREAM_DSA_20261002.md` |

### 测试结果（`results/`）

| 文档 | 轮次 | 要点 |
|---|---|---|
| `RESULTS_FT_COLD32K_20261002.md` | 第 0 代前 | 冷 32K 首 token 基线 |
| `RESULTS_FT_PAPER_HEADROOM_20261003.md` | E0-R000 | 带宽、失误率、专家槽余量 |
| `RESULTS_DEV_D0_20261003.md` | E0-R005 | D0 逐层埋点 |
| `RESULTS_DEV_D1_20261003.md` | E0-R006/R007 | 层优先长预填 |
| `RESULTS_DEV_D3_20261003.md` | E0-R008/R009 | 多锚检查点 |
| `RESULTS_E1_20261003.md` | E1-R000 至 R003 | 第 1 代各轮实测 |

### 解读与验收（`reports/`）

| 文档 | 范围 |
|---|---|
| `REPORT_E1_20261003.md` | E1-R001、64K 补测、E1-R002、E1-R003 回放的解读；面板数据修正清单；编辑器 M1 验收 |

### 依据（`research/`）

| 文档 | 内容 |
|---|---|
| `RESEARCH_REPORT_UPSTREAM_DSA_20261002.md` | 上游代码阅读：专家缓存、hybrid 搬运、带宽档 |
| `RESEARCH_TTFT_DECODE_OPT_20261003.md` | 首 token 和解码优化调研 |
| `REVIEW_ASTRO_MULTIUSER_20261003.md` | Astro 多用户研发方案评审 |
| `REVIEW_GPT6_DIRECTION_20261003.md`（已在 `research/`） | GPT-6 论文方向稿和第一阶段协议稿评审：TP 下每卡专家驻留账、单卡核心问题改为按遍数计成本（H0）、TP 数值门、四卡组法待决定 |
| `REPLY_V31_MERGED_REVIEW_20261003.md` | 对 Grok 与 GPT-6 合并审阅的回复与 v3.2 定版说明：开关四格的重读、状态层逐层误差分析、容差的独立标定 |
| `REPLY_GPT6_V3_REVIEW_20261003.md` | 对 GPT-6 第三版审阅（`paper/openai/`）的逐条回复：12 条接受、R4 部分接受；补错相位重叠解码、有限合批、D6 取舍、64K 算力上限 |
| `REVIEW_PAPER_FINAL_20261003.md` | 终稿评审：对照伯克利原文的方向判断、数学审阅、GPT-6 稿把关、上游代码挂点与工作量、单卡目标可达性、下一步排序 |
| `_shared/PAPER_COMPARE_KT_FT_20261003.md` | KT 与 FT 论文对比（跨框架，留在 `_shared/`） |

### 论文（`paper/`）

| 文档 | 说明 |
|---|---|
| `FreeToken_MultiGPU_CoExec_v4.0.html` | **当前稿 v4.0（第一阶段定稿，HTML，arXiv 排版）**。主题：共享资源约束下主存卸载 MoE 的多 GPU 低延迟协同执行；源文件在 `paper/src/`，用 `python paper/src/build_v4.py` 生成；数据版本 FTD-20261003-1。`paper/README.md` 是论文目录与版本历史。
| `archive/freetoken-4090-agents_v3.2.md` | 第 3.2 版留档。v3.2 时的说明：并入 batch17 开关四格（冷 +一遍、热 0）与 batch18/19 状态层比对（#577 非逐位无损）；不接受 19:22 的开关撤回结论。以下为 v3.1 时的说明：第 3.1 版。按 GPT-6 对 v3 的审阅修订：条件上界、重叠模型、有限合批、四层正确性准入、错相位重叠解码 D14。以下为 v3 时的说明：Agent 直接改这个文件。H0 改为「继承原文的遍数现象，研究其后果」；新增 PCIe 预算、遍数排队、单卡可达性；并入 E1-R003-v4/v5 与地板数据；数字直接写明并注〔轮次〕 |
| `archive/freetoken-4090-agents_v1.md` | 第 1 版留档 |
| `archive/freetoken-4090-agents_v2_draft.md` | 第 2 版留档 |
| `archive/freetoken-4090-agents_v3.md` | 第 3 版留档 |
| `archive/freetoken-4090-agents_v3.1.md` | 第 3.1 版留档 |
| `openai/` | GPT-6 对 v3 的审阅意见与复算包；回复见 `research/REPLY_GPT6_V3_REVIEW_20261003.md` |
| `archive/GPT6_Astro_方向稿_…`、`archive/GPT6_Astro_协议稿_…` | GPT-6（Astro）方向稿与协议稿留档；取舍见 `research/REVIEW_PAPER_FINAL_20261003.md` |

---

## 3. 旧文档迁移对照（未执行，已交给开发 agent）

在 `freetoken/` 目录下执行的 shell 命令都被本机钩子拦下了，读取已有文件的操作也被拦，所以这一轮没有移动旧文件。迁移由开发 agent 按 `tasks/TASK_DOCS_MIGRATION_20261003.md` 一次性完成，对照表如下：

| 现在的位置（`freetoken/`） | 目标位置 |
|---|---|
| `PROJECTION_PERF_PLAN_20261003.md` | `plans/` |
| `DEV_PLAN_FT_QWEN38_20261003.md` | `plans/` |
| `DEV_NEXT_FT_QWEN38_20261003.md` | `plans/` |
| `DEV_NEXT_D3_20261003.md` | `plans/` |
| `TASK_UPSTREAM_PRS_HYBRID_20261003.md` | `tasks/` |
| `TASK_FT_PAPER_HEADROOM_20261003.md` | `tasks/` |
| `TEST_TASK_FT_COLD32K_TTFT_20261002.md` | `tasks/` |
| `RESEARCH_TASK_UPSTREAM_DSA.md` | `tasks/` |
| `RESULTS_FT_COLD32K_20261002.md` | `results/` |
| `RESULTS_FT_PAPER_HEADROOM_20261003.md` | `results/` |
| `RESULTS_DEV_D0_20261003.md` | `results/` |
| `RESULTS_DEV_D1_20261003.md` | `results/` |
| `RESULTS_DEV_D3_20261003.md` | `results/` |
| `RESULTS_E1_20261003.md` | `results/` |
| `RESEARCH_REPORT_UPSTREAM_DSA_20261002.md` | `research/` |
| `RESEARCH_TTFT_DECODE_OPT_20261003.md` | `research/` |
| `REVIEW_ASTRO_MULTIUSER_20261003.md` | `research/` |

迁移后要同步的引用：

- **本目录内文档之间的链接**：`README.md` 7 处，`PROJECTION_PERF_PLAN` 9 处，`TASK_UPSTREAM_PRS_HYBRID` 4 处，`TASK_FT_PAPER_HEADROOM` 4 处，其余文档各 1–2 处。
- **面板数据里的「来源」文字**：`devrun.json` 39 处，`rounds.json` 10 处，`rounds_seed_E0.json` 10 处，`research.json` 1 处，`TASK_DEVRUN_DASHBOARD_20261003.md` 14 处。这些只是显示用的文字，服务端不按路径读文件，所以不会报错，只会过时。由面板 agent 按上表替换。
- **代码和脚本里的注释**：`scripts/agent_trace.py`、`scripts/probe_ft_cold32k.py`、`_shared/probe_cold32k.py`、`_shared/dev_d0/` 下的若干文件。只是注释，可以顺手改，也可以不改。

---

## 4. 待测试队列

| 顺序 | 内容 | 类型 | 状态 | 依据 |
|---|---|---|---|---|
| 1 | 面板数据修正 7 项 | 数据 | 待办 | `reports/REPORT_E1_20261003.md` 第 6 节 |
| 2 | 生产口径重测：层优先加 #578，窗口 65,536，`taskset -c 1,3-47`，不开 D0 | 测量 | 待测 | 报告第 8 节第 2 步 |
| 3 | E1-R008：锚封顶开、关 A/B（12 轮 Agent 轨迹），D0 补请求编号和切段原因。论文 H0 的第一个实验 | 测量，加一个开关 | 待测 | 报告第 5.3 节、第 8 节第 5 步；论文第 2 版第 6.4 节 |
| 4 | E1-R002b：hybrid 复测，避开 0、2 号核 | 测量 | 待测 | 报告第 4.2 节、第 8 节第 3 步 |
| 5 | E1-R005：多会话真实并发和停顿基线。并入：GPT-6 协议稿 E1 的三个配对条件（不插入、等时长空等、真实预填）和恢复后 1、8、32 步窗口，D0 补逐步缺失数和 H2D 计数；两个短后缀轮次同时到达时是否共用一遍专家流 | 测量 | 待测 | `PROJECTION_PERF_PLAN` §7、§8；`research/REVIEW_GPT6_DIRECTION` 第 3.3、7 节 |
| 6 | E1-R003 运行期：带 `--edit-at-idx` 的编辑后轮次 | 测量 | 进行中 | `TASK_UPSTREAM_PRS_HYBRID` |
| 7 | 命中对重算的确定性：先测重算对重算，再看 logit 差 | 测量 | 待测 | 报告第 5.3 节 |
| 8 | E1-R006 探针：短后缀、2399 专家槽（64K 窗口已测；锚封顶并入第 3 项） | 测量 | 待测 | `PROJECTION_PERF_PLAN` §7 |
| 9 | E1-R007：路由轨迹导出 | 埋点加离线分析 | 待测 | `PROJECTION_PERF_PLAN` §7 |
| 10 | G0：TP2、TP4 每卡显存账（按实际加载路径），决定四卡怎么组和论文第 10 节 | 分析，基本不占 GPU | 待办（用户已定：先做 G0 再定四卡组法） | `tasks/TASK_G0_TP_MEMORY_20261003.md` |
| 11 | 论文第 2 版导入 8098 | 取消 | 取消 | 用户决定：论文只在本地改，远程论文编辑器已删除 |

---

## 5. 论文怎么管

论文就是 `freetoken/paper/` 里的文件。当前稿是 `paper/README.md`，用过的旧稿放 `paper/archive/`。Agent 直接改当前稿。8098 上不再有论文页面和论文接口。

1. **不往 8098 上传，也不在浏览器里改。** 远程论文编辑器、`/api/papers`、导入脚本和写入口令已删除。
2. **一篇当前稿。** 大改就改当前稿；上一版移入 `paper/archive/`，文件名写明版本，不另开页面。
3. **数字写明，并注明轮次。** 例如「冷 32K 首 token 6.60 / 6.49 s（E1-R001）」。`{{r:}}` 不会再被页面自动替换。没有轮次支撑的句子标成待测，不写成已经测过。


---

## 6. 计划体系（`plan/`）

测试、开发与数据版本的总入口，见 `plan/README.md`。

| 目录 / 文件 | 用途 | 执行者 |
|---|---|---|
| `plan/00_规则_测试存储与数据版本.md` | 原始工件存储、轮次 ID、round.json 只追加、数据发布 FTD 与论文版本绑定、执行纪律 | 全体 |
| `plan/01_测试与调研/` | T01–T21 测试与调研卡；结果写 `results/`；新T17按同结构冷参照判据执行 | 低成本模型（不改代码） |
| `plan/02_开发任务/` | 卡D01–卡D18 开发卡；每张写明需要01验证的卡号；卡D14调度与卡D16套件先行 | 高级模型 |
| `plan/data_releases/` | 数据发布清单（首个为 FTD-20261003-1，对应论文 v4.0） | 总负责人 |

第 4 节的待测队列，以后以 `plan/README.md` 的状态表为准。T08 的生产重测窗口用 73,728（65,536 放不下 65,412 token 的提示加输出）。

当前优先级与判据以 [20261005权威任务书](plan/PLAN_20261005_重新规划.md) 为准。R031已独立封存为GDN算子形状诊断kept，不能代替新T17；历史R023 not_met保留。阶段A未闭合前，卡D17集成和阶段B GPU测量继续等待；MTP冻结，卡D13保持真正TP路线。
