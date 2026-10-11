# 02 开发任务：开发手册

2026-10-09补充：新增[卡D19批不变性](D19_批不变性_只读调研.md)，归E3，只读源码/官方资料调研完成，未排GPU、不阻塞发布。当前授权以[01:00指令](../ROOT_EXECUTION_DIRECTIVE_20261009.md)、[01:30覆盖](../NIGHT_PREAUTH_20261009.md)、[08:30补充](../SUPPLEMENT_20261009_0830.md)依次覆盖冲突处；旧版本基线说明保留为历史。

> **版本声明（2026-10-03 用户决定）**：后续测试与开发统一在**第 2 代基线 `E2-base`** 上进行。E2-base = `40fd5d4` + #578 + #577 + 状态落盘钩子 + D01 + D02，新增功能默认关闭或保持现状；构建见 `02_开发任务/D00`，立项测量见 `01_测试与调研/T00`。
> - E2-base 过门之前，只有不依赖它的卡可以开工：T01、T02、T12–T15（不占 GPU），以及只读复核。
> - 各卡中写的第 1 代树（40fd5d4 / 80943fd / c721c74 / 97bc62c）只用于复现第 1 代历史数据。新轮次一律以 E2-base 为父树，轮次 ID 用 `E2-R<序号>`，由总负责人分配。
> - 每个新轮次的 `round.json` 必须写 `base.code_version = "E2-base@<短提交号>"`。

> 执行者：高级模型。规则全文见 `../00_规则_测试存储与数据版本.md`。论文只由总负责人修改；验收数必须来自 01 卡。
> **卡号与机制代号不是一回事**：卡号 `D00`–`D18` 是开发卡序号（写作「卡D14」）；机制代号沿用论文（D0 埋点、D1 层优先、D3 多锚检查点、D6 遍内插解码、D12 每轮一遍、D13 短后缀按需搬运、D14 错相位重叠解码）。卡里提到机制时一律写「机制 D12」这类全称。

---

## 1. 代码树与基点

| 树 | 分支 | commit | worktree（远端） | 用途 |
|---|---|---|---|---|
| 上游固定提交 | `origin/main` | `d3512b4` | 本地 `freetoken/upstream-flashml/`（只读参照） | 论文 §2.2 挂点的行号依据 |
| 第 1 代基线 | `dev/d-series-clean` | `40fd5d4` | `/data2/FreeToken/wt/e1r000b` | hybrid 诊断（D08）基点 |
| #578 树 | `exp/e1r001b-pr578` | `80943fd` | `/data2/FreeToken/wt/e1r001b` | 生产口径、多会话（D02、D06、D07）基点 |
| #577 树 | `exp/e1r003-pr577` | `c721c74` | `/data2/FreeToken/wt/e1r003` | E1-R008（D01）、D3 触发点（D09）基点；**不含 #578** |
| 落盘钩子树 | `exp/e1r003-statedump` | `97bc62c` | `/data2/FreeToken/wt/e1r003sd` | 状态层工具（D03）、uid=8（D05）基点 |
| **第 2 代统一基线** | `e2/base` | 标签 `E2-pre`@`3db7b50`，`E2-base` 未打 | `/data2/FreeToken/wt/e2base` | **D00 构建；之后所有新开发卡的父树**（上面四行只用于复现第 1 代） |
| D01 开发交付 | `exp/e1r008-anchorcut` | `f91054b`（父提交 `E2-pre@3db7b50`） | `/data2/FreeToken/wt/e1r008`；本地 `development/e2d01/` | 独立切段开关、段原因与快照计数；单测新增 14 例通过，待 01 验证 |
| D02 开发交付 | `exp/e1-ms` | `23f2e2c`（父树 D01 `f91054b`，祖先 `E2-pre@3db7b50`） | `/data2/FreeToken/wt/e1ms`；本地 `development/e2d02/` | 末段即时落盘、逐步计数与解码时间线；新增 30 个测试通过，ABAB 开销 2.404620%；[交付记录](D02_交付记录_20261004.md)，待 01 验证 |

远端源码主检出 `/data2/FreeToken/src/FreeToken`（当前在 `exp/e1r001-pr578` @ 184c965）。**新工作一律开新分支 + 新 worktree**：

```bash
git -C /data2/FreeToken/src/FreeToken worktree add -b exp/<名字> /data2/FreeToken/wt/<名字> <基点 commit>
cp /data2/FreeToken/wt/e1r003/python/freetoken/kernel/_cpu_moe*.so /data2/FreeToken/wt/<名字>/python/freetoken/kernel/
cp /data2/FreeToken/wt/e1r003/python/freetoken/kernel/_pinned_tensor*.so /data2/FreeToken/wt/<名字>/python/freetoken/kernel/
```

（worktree 不带编译产物，不拷 `.so` 时 `--ple-backend pinned` 起不来；`RESULTS_E1` 工装变更。）

## 2. 必须遵守的工程约束

1. **默认关**：新功能只有「关闭 / 影子 / 启用」三种模式，默认关闭（论文 §11）。默认路径必须与父树逐位一致——由 01 的 T16 验收。
2. **热路径不得无条件读新属性**：本项目已三次踩坑（`PrefillManager.layer_major`、`Scheduler.d3_extra_anchor_ids`、`scheduler.py:396-398` 解码热路径读 `d3_extra_anchor_ids`；论文 §9.3「工装缺陷三连」）。新属性必须在类上声明默认值；对应加进 `tests/scheduler/test_switch_defaults.py` 一类的默认值测试。
3. **开关可见**：新开关优先做成 `ServerArgs` 字段（出现在 `serve.log` 的 `Parsed arguments`，`serve_args_diff.py` 可见）；仅开发埋点可以用环境变量 `FT_DEV_*`，必须在 `SERVE_CMD.txt` 中可见，并在 D0 或日志里打印「已启用」一行。
4. **失败关闭**：工具与埋点在找不到输入、字段缺失、两侧集合不等时报错退出，不返回「看起来一致」（`state_eq.py` 先例）。
5. **CRLF**：D 系列文件从 `fafe4e5` 起整文件 CRLF；跨树搬改动用 `format-patch | 剥 CR | git merge-file` 三方合并，不要直接 cherry-pick（`RESULTS_E1` 回放坑）。
6. **测试基线**（c721c74）：`pytest tests/scheduler tests/kvcache` = 2 failed / 370 passed / 1 skipped，2 例已知失败是 `tests/scheduler/test_abort_inflight_prefill.py::test_prefix_commit_sentinel_guard`（172 行）与 `::test_post_terminal_overlap_step_is_dropped`（202 行），成因是解码热路径无条件读 `self.d3_extra_anchor_ids`（`scheduler.py:398`）。新改动**不得增加失败数**。上游 `tests/kernels/test_e4m3_compat.py::test_forced_emu_matches_native` 在纯 d3512b4 上也失败，不计入。
7. **测试运行**（远端，CPU）：`cd /data2/FreeToken/wt/<名字> && PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache -q`。
8. **开发自检可以起服务**，但同样受规则 §6 门禁约束（单写者、GPU 锁、工作树断言）；自检读数不作验收数，不写入 `ft_rounds/`（写到 `/data2/FreeToken/runs/dev_<卡号>/`）。
9. **不改已关闭工件、不改论文、不改 01 卡**。发现 01 卡命令与交付不符，在本卡「交付记录」写明，由总负责人改卡。

## 3. 卡片清单

| 卡号 | 内容（机制） | 优先级 | 估计人日 | 依赖 | 交付后由 01 验证 |
|---|---|---|---|---|---|
| D00 | **第 2 代统一基线 E2-base**：40fd5d4 + #578 + #577 + 落盘钩子 + D01 + D02（先出 `E2-pre`，D01/D02 在其上开发） | P0（阻塞全部 GPU 卡） | 1–2 | D01、D02 | T16（gate-D00）→ T00 |
| D01 | 机制 D12 第一步：锚点切段独立开关 + 逐段切段原因 | P0 | 1–1.5 | `E2-pre`（D00 第 0–3 步） | T16（gate-D01）→ T03 |
| D02 | 机制 D0 补字段：请求编号、段原因、逐段 H2D/D2D、逐步缺失数、解码时间线；末段落盘缺陷 | P0 | 2–3 | `E2-pre`（字段名与 D01 一致） | T16（gate-D02）→ T05、T07（可选复核） |
| D03 | 状态层工具：参照臂中间边界落盘、逐层包络、固定后续 token 的 logits 比对（第 3 层门） | P0 | 3–5 | 无 | T04 阶段 2、T10 阶段 2 |
| D04 | 工装修正：`round.json` 追加式写入器、轮次收尾脚本、比对结论行按比较对象生成标签 | P0 | 1–1.5 | 无 | 01 全体使用；T01 之后的所有收尾 |
| D05 | uid=8 缺 donate：按 T11 归类结果补钩子或修缺陷 | P1 | 0.5–2 | T11 | T16（若改默认路径）+ T11 阶段 2 复跑 |
| D06 | E1-R005 多会话测量工装（客户端 + 开发用暂停端点） | P1 | 2–3 | D02 | T16（gate-D06）→ T05 |
| D07 | E1-R007 路由轨迹导出钩子 + 离线分析 | P1 | 2–3 | D02（请求编号） | T16（gate-D07）→ T06 |
| D08 | hybrid 执行器诊断埋点（每层服务时间分解） | P2 | 2–3 | 无 | T16（gate-D08，父树 40fd5d4）→ T09 |
| D09 | 机制 D3：基于 #577 的触发点（层优先子块边界、多锚） | P2（后置） | 5–8 | T03 结论、T04 阶段 2 结论 | T16 → 新轮次（届时建卡） |
| D10 | 机制 D14：错相位重叠解码可行性原型（**高风险**） | P3 | 读码估计 10–20（本卡只做 3–5 的可行性原型） | T05 时间线 | 新轮次（届时建卡） |
| D11 | 机制 D6：遍内插解码（**后置**） | P3 | 15–25 | T05 基线、T14 调研 | 新轮次 |
| D12 | 机制 D13：短后缀按需搬运（**后置**） | P3 | 3–6 | T06 真实后缀分布 | 新轮次 |
| D13 | TP 原型（**后置**） | P3 | 15–30 | T12（G0） | 新轮次 |

人日均为读码估计（论文附录 D），不是交付承诺。


### 2026-10-05 新增与改动（详见 `../PLAN_20261005_重新规划.md` §5、§6）

| 卡 | 内容 | 阶段 / 优先级 | 估计人日 | 依赖 | 01 验证 |
|---|---|---|---|---|---|
| 卡D14（改） | 缺陷 K1 修复收尾 + 开发用预填调度参数 `FT_DEV_PREFILL_SCHEDULE` | A / P0 | 1–3 | — | T16 → T17 |
| **卡D16（新）** | 等价测试套件（借鉴 Strata 的 batch / parking / interleave / cache-parity 测试设计） | A / P0 | 2–3 | 卡D14 的调度参数；复用卡D06 客户端、卡D03 工具 | T17、T20 |
| **卡D17（新）** | E2-base.1 集成 = E2-base + 卡D14 + 卡D06 + 卡D07 + 卡D16 工具 | A / P0 | 1 | 卡D14 过 T17 | T16 → T20 |
| **卡D18（新）** | 客户端参数化：`probe_ft_cold32k.py`、`benchmark_client.py` 支持端口与模型名（默认不变），**已交付** | A / P1 | 0.5 | — | T19 使用 |
| 卡D08（改写） | hybrid 执行器：诊断 + 移植 Strata 线程池 + NUMA 选项；基点 E2-base.1 | C / P1 | 4–7 | 卡D17 | T16 → T09 |
| **卡D15（新）** | 自适应专家缓存（画像 + 在线置换，默认关闭） | C / P1 | 4–8 | 卡D17、T06 | T16 → T21 |
| 卡D12（改） | 短后缀按需搬运，参照 Strata 的 `stream_all_min` 阈值方法 | C / P2 | 2–4 | T06 | — |
| 卡D06 / 卡D07 | 剩余 G3/G4 改在 E2-base.1 上做 | B / P1 | — | 卡D17 | T05 / T06 |
| 卡D13 | TP：**按原计划不变** | D / 后置 | 15–30 | 四卡、G0 | — |

## 4. 卡片生命周期与交付记录

状态：`待办 → 进行中 → 已交付，待 01 验证 → 完成 | 退回 | 阻塞`。只有对应 01 卡（至少 T16）通过后才能标「完成」。

每张卡末尾的「交付记录」由 02 执行者填写，01 卡直接抄用，**格式固定**：

```
- 分支 / commit（7 位）：exp/<名字> @ <commit>
- worktree：/data2/FreeToken/wt/<名字>
- 父树 worktree / commit：…
- 新增开关（名字 / 类型 / 默认值 / ServerArgs 字段名或环境变量名）：…
- 新增脚本（远端路径 / 用法一行）：…
- 测试：命令 + 结果（passed/failed/skipped 数，与基线对比）
- 开发自检工件：/data2/FreeToken/runs/dev_<卡号>/…
- 01 读取新字段的命令（逐字可执行）：…
- 已知限制：…
```
