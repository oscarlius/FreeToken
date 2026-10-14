# op-hak 任务 B：按成本模型决定是否切段（M1 完整版）——实现、默认关闭等价门与 ABBA 实测（2026-10-11 夜，主会话 freetoken-06）

> 读者是执行者 op-hak。通用规则沿用 `plan/OPHAK_TASK_A_ANCHOR_CUT_20261011.md` §0 与补充 1（窗口任何终态都必须恢复 481）。本文件发出后冻结（0444），更正另发补充。用户已确认本任务（菜单第 1 项），并已知悉窗口约 45–50 分钟、超过 30 分钟。**在任务 S 完成之前不得开 GPU 窗口。**
>
> **预登记**：`development/anchor_cut_accounting_20261011/PREREG_TASK_B_v2.json`，SHA256 `8df5ee4901795d287bed22cfaadbaef3515c89f530c4f9df26a5798489f9152d`，下发前已封存。v1（`2b96954a…`）在下发前自检中被替代：切段与 cached 的预测不变，只改了 G5 的措辞（见 `supersedes` 字段），替代前未见任何数据。

## 1. 为什么做、做什么

- 任务 A / A2 证实：生产开着的锚点切段让热轮白付一遍（约 2.66 s），切出的段也不产生可复用快照；但直接关掉锚点切段，87K 长会话上出现 OOM（事件 E1）。
- 成本模型给出的规则：搬一遍（2.78 s）≈ 重算 14K token；一刀只有在"预计省下的重算 > 14K ÷ P(改写)"时才值得切。
- **新机制**：新增启动参数 `--prefill-anchor-cut-min-tokens N`。只有本段待预填的 token 数（`remain_len = input_len − cached_len`，prefill.py:166）超过 N 时，才按锚点切段。**默认 N = 0，与现行为逐位相同。** 实测取 N = 32768。
- 按模拟器（`segment_sim_v2.py`，策略 `thresh32k`）：热轮全部变成一段；seed_real 冷 87K 仍切成 22,272 + 64,828（与生产相同）；T2 冷 12K 不再切；各轮 cached 不变。

## 2. P1：代码（只在新工作树里改）

- **工作树**：在 release-e2 所在仓库执行 `git worktree add -b m1/cut-min-tokens SRV/wt/m1-cutmin-20261011 481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`。不改 release-e2 本身；**只在本地提交，不得 push**。
- **编译扩展**：新工作树没有 `.so`（git 不跟踪）。按 T16（`wt/d09_fix_20261011`）的做法，把 release-e2 的 `python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so` 与 `_pinned_tensor.cpython-310-x86_64-linux-gnu.so` 以符号链接放到候选的同一位置。校验两者 SHA256 与工装常量 `EXTENSION_SHA256`（`_cpu_moe` 10a2bd83…、`_pinned_tensor` 07701be2…）一致；链接后 `git status --porcelain --untracked-files=no` 为空。
- **改动点**（行号为 release-e2 的，以读码为准）：
  1. `scheduler/config.py`：在第 21 行 `prefill_anchor_cut` 旁增加 `prefill_anchor_cut_min_tokens: int = 0`。`ServerArgs` 继承 `SchedulerConfig`（args.py:38），**不要在 ServerArgs 里重复声明**。
  2. `server/args.py`：在 `--no-prefill-anchor-cut`（约 409 行）旁增加 `--prefill-anchor-cut-min-tokens`，`type=int`，`dest="prefill_anchor_cut_min_tokens"`，`default=ServerArgs.prefill_anchor_cut_min_tokens`，帮助文字："只有本段待预填 token 数超过 N 时才按锚点切段；0 表示与原行为相同"。argparse 结果经 `ServerArgs(**kwargs)`（约 940 行）构造，无需别的接线。
  3. `scheduler/scheduler.py:141`：构造 `PrefillManager` 时加 `prefill_anchor_cut_min_tokens=config.prefill_anchor_cut_min_tokens`。
  4. `scheduler/prefill.py`：`PrefillAdder`（字段在约 68 行）与 `PrefillManager`（约 362 行）各加同名字段，默认 0；`schedule_next_batch` 里构造 `PrefillAdder` 处（约 402 行）一并传递；179 行条件末尾加 `and remain_len > self.prefill_anchor_cut_min_tokens`。`_schedule_dev_prefill` 里 `prefill_anchor_cut=False` 的路径（约 483 行）不动。
- 不得做任何其他改动。提交一次，记录提交哈希与 `git diff --stat`。
- **单测**（CPU，照 `tests/scheduler/test_prefill_anchor_cut_switch.py` 与 `test_anchor_cut_scheduler_wiring.py` 的写法，新文件放同目录）：
  - N = 0 时，在含锚点的合成 token 序列上，切段结果与 release-e2 完全相同；
  - N = 32768 时：`remain_len ≤ 32768` 不切；`remain_len > 32768` 与 release-e2 相同；
  - 命令行解析：默认 0；给定值能经 ServerArgs → Scheduler 传到 `PrefillManager` 与 `PrefillAdder`；
  - **现有测试基线**：先在 release-e2 上跑一次 `tests/scheduler` 记下结果（release-e2 本身可能有失败项）；候选上同一命令不得新增失败。
- **离线核对**：在 CPU 上把 20 个冻结 payload（任务 A 的 `inputs/`）喂给候选的切段规则（按 `segment_sim.py` 的做法，但调用候选代码，或用单测已覆盖的同一实现），确认 N = 0 与 N = 32768 的切段，与预登记的 `on_segments` / `thresh_segments` 逐轮相同。

## 3. P1：工装与恢复包

- **工装**：沿用任务 A2 的 `task_a_runner.py`（112917c56034），改三处，配单测：
  1. 服务定义可指定构建：release-e2 或候选工作树的 `PYTHONPATH`（与 T16 相同的方式）。启动前用同一环境执行 `python -c "import freetoken.scheduler.prefill as m; print(m.__file__)"`，路径必须落在该服务应有的工作树下，否则拒绝启动（**构建门**）。
  2. B 臂额外参数 `--prefill-anchor-cut-min-tokens 32768`；启动后在 serve.log 的 "Parsed arguments" 中核对 `prefill_anchor_cut_min_tokens` 的值（A 臂为 0，B 臂为 32768），不符即停（**参数门**）。
  3. **单服务 OOM 处理**：某服务出现 OOM 或 worker 退出标记时，记下服务与轮次，按正常流程关掉该服务（只关我方进程），继续下一个服务；**同一窗口第二次 OOM：停窗并恢复 481**。
- 轨迹为 seed_real 第 0–7 轮 + T2 第 0–11 轮（与任务 A 相同的 20 个 payload，加 warmup，顺序同任务 A）。
- **恢复包 restore13**：以 `restore12` 为模板复制，**不复制 `EXECUTION_TIME_PREFLIGHT.json`**（那是 restore12 执行时生成的文件）；只替换 `-12 → -13` 两个精确字符串；`run_dir` 为 `RESTORE481-MORNING-20261011-13`；`independent_review_sha256` 填本指令的 SHA。pytest 7 passed，门链通过。**恢复的仍是 release-e2（481d3a7），不是候选。**
- **CPU 演练**：桩服务跑通 5 个服务；反向对照五项：
  - (a) 候选默认参数的输出被桩故意改动一处，T16-lite 能判"不等"；
  - (b) B 臂漏加参数，参数门拒绝；
  - (c) 某服务的 `PYTHONPATH` 指错工作树，构建门拒绝；
  - (d) 桩让第 3 个服务 OOM：工装关掉它，继续第 4 个；
  - (e) 桩让两个服务 OOM：工装停窗并走恢复流程。

就绪后在协调日志写"op-hak：任务 B P1 就绪"，发消息给我；等主会话写"任务 B 放行"再开窗。

## 4. P2：GPU 窗口（任务 S 完成且放行后）

### 4.1 服务（顺序固定）

| 序 | 名称 | 构建 | 额外参数 | 用途 |
|---|---|---|---|---|
| 1 | `R0` | release-e2 | 无 | 默认关闭等价门的基线 |
| 2 | `C_A1` | 候选 | 无（N = 0） | 等价门 + A 臂 |
| 3 | `C_B1` | 候选 | `--prefill-anchor-cut-min-tokens 32768` | B 臂 |
| 4 | `C_B2` | 候选 | 同上 | B 臂 |
| 5 | `C_A2` | 候选 | 无 | A 臂 |

每个服务：warmup + seed_real 0–7 + T2 0–11，共 21 条；`max_tokens` 32；其余同任务 A / A2（不加冷标记、首 token 只认非空增量、worker 退出即时识别、显存采样）。

### 4.2 停服与恢复

W0 至 W3 同任务 A2：停服用生产当前审批号所对应包的 `stop_approved_restore.py`（以 `production.active.json` 为准；任务 S 后若仍为 -12，即 restore12）；W5 用 restore13。若任务 S 结束时 481 不在服务，W0 由主会话另发补充。总时限 60 分钟，**预计停服约 45–50 分钟**。

## 5. 判读（全部取自预登记 v2）

| 项 | 判据 | 读法 |
|---|---|---|
| T16-lite（默认关闭等价） | R0 对 C_A1：20 轮的切段、cached、输出全文逐字相同 | 全部相同：成立；任一不同：不成立，B 臂结论只作参考 |
| G1 | C_A1/C_A2 的切段与 cached 等于 `on_segments`；C_B1/C_B2 等于 `thresh_segments` | 任何一轮不符：写"模型在第 k 轮不成立" |
| G2 会变的热轮 | 两条轨迹中 class 为 `changed` 的 14 轮，Δ = A 臂均值 − B 臂均值 | 中位数 ∈ [2.3, 3.0] 且每轮 ≥ 1.8 s：成立；中位数 < 1.0：不成立；其余：部分成立 |
| G2 不变的轮 | T2 第 2、3、9、11 轮 | \|中位数\| ≤ 0.3 s：成立 |
| 冷轮 | seed_real 第 0 轮（预测不变）、T2 第 0 轮（预测少一遍；A2 中同类冷轮 Δ 为 3.545 s，原因未核实） | 只报告 |
| 漂移 | 同臂两服务同轮相差 `|a−b|/max(a,b)` > 10% 的轮次 | 超过 3 轮：G2 降级为仅供参考 |
| G3 | 同臂两服务同轮输出逐字相同 | 不同：写首个不同字符的位置 |
| G5 | B 臂两个服务都跑完、无 OOM | 任一 B 臂服务 OOM：判"阈值策略未避开 E1"，该参数不进生产；照实报告服务、轮次、显存轨迹 |

某服务因 OOM 中途关停时，它已跑完的轮次照常计入；缺失的轮次在表中标"缺"，G2 只用两臂都有数据的轮次。

## 6. 报告

`RESULT_B.md`（0444）：代码提交哈希与 diff 统计、单测与测试基线对比、构建门与参数门记录、T16-lite、逐服务逐轮表、G1–G5、显存轨迹、W5 记录。完成后发消息给 freetoken-06。**是否把该参数用到生产，由用户另行决定，本任务不改生产配置。**

## 7. 主会话下发前自检

| # | 清单项 | 本指令的情况 |
|---|---|---|
| 1 | 终点指标 | 每轮首 token |
| 2 | 预测是否事先写死 | 切段由 `segment_sim_v2.py` 给出（与旧策略结果逐一相同，未改旧逻辑）；Δ 区间沿用 A2 已验证的一遍时长。两条轨迹同服务先后跑互不影响：seed_real 的快照都在 22,208 之后，T2 最长 21,976 token，任务 A 已实测 |
| 3 | 目标负载 | 包含 87–95K 的 seed_real（目标负载）与 T2 |
| 4 | 默认路径不变 | 原条件已要求 `chunk_size > 64`，而 `chunk_size ≤ remain_len`，故 N = 0 时新增的 `remain_len > 0` 恒真，行为逐位相同；用 T16-lite（R0 对 C_A1）实测证明 |
| 5 | E1 风险（已更正） | 冷 87K 的切段与开臂相同，冷轮显存峰值相同；**但热轮变成单段，形状与出过 E1 的关臂热轮相同，E1 根因未证，不能说已避开**。处理：G5 是正式判据；单服务 OOM 时关掉该服务、继续下一个，第二次 OOM 停窗恢复 |
| 6 | 接线已读码核实 | ServerArgs 继承 SchedulerConfig（args.py:38）；`ServerArgs(**kwargs)`（约 940 行）；`remain_len`（prefill.py:166）是本段起点到末尾的长度，与模拟器一致 |
| 7 | 候选能真正跑起来 | 新工作树缺 `.so`，按 T16 链接并核对 SHA；构建门核对实际导入的工作树；参数门核对 serve.log 的解析结果 |
| 8 | 阈值依据 | 一遍 ≈ 重算 14K token（冷预填 4,700–5,100 tok/s 实测）；32K 对应 P(改写) ≳ 0.43 |
| 9 | 生产风险 | 不改生产；恢复的是 release-e2；restore13 不带 restore12 执行期生成的文件 |
| 10 | 窗口时长 | 约 45–50 分钟，超过 30 分钟，按规则已先向用户说明 |
| 11 | 今天的教训 | 默认路径改动必须有等价门；同类比较；ABBA；首分片空包；不加冷标记；worker 退出即时识别 |
| 12 | 局限 | 等价门只覆盖层优先（生产配置），不含普通预填路径；改写概率 P 未实测，32K 是保守取值；T2 上阈值策略与关闭锚点切段等价（T2 最长 12K），B 臂 T2 数据是对 A2 的复现，新信息在 seed_real |
