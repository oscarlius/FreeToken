# op-hak 任务 A：P1 就绪记录（CPU 阶段，2026-10-11）

- 指令：`plan/OPHAK_TASK_A_ANCHOR_CUT_20261011.md`（SHA256 `b8232e31efca99be88addc44f55d30bea76f243d411e9b9b6cb03c02363599f4`，本地与服务器一致，0444）
- 预登记：`development/anchor_cut_accounting_20261011/PREREG_TASK_A.json`（SHA256 `0e1708bf033f26ec5f5cde94a1cd3ff86e786c854990033df8246a04006814b9`，两侧一致）
- 执行者：op-hak
- 结论：**P1（H1–H5）全部完成。未开窗，未停 481，未碰 GPU。等待主会话在协调日志写"任务 A 放行"。**

## 1. 本阶段做了什么，没做什么

| 项 | 做了 | 没做 |
|---|---|---|
| H1 输入冻结 | 20 个 payload（seed_real 8 个、T2 12 个）写到 `inputs/`，并逐轮核对 | — |
| H2 工装 | 运行器、桩服务、判读脚本、单元测试；单测 18 项通过 | 没有在 GPU 上运行过真实服务（P2 才能做） |
| H3 恢复包 | `restore12/` 构建完成，门链通过，diff 已逐条核对 | 没有执行恢复（只在 W5 执行） |
| H4 演练 | 五项演练全部完成，见第 4 节 | 演练用桩服务，只证明工装路径，不是证据 |
| H5 就绪 | 本文件 | — |

资源：演练进程绑定在 CPU 核心 0 与 2 上，481 占用的是核心 1 与 3–47，两者不重叠。演练期间 481 保持 serving，`active=0`，`backend_epoch=0`，`restart_attempts=0`。

## 2. H1 输入冻结

- `INPUTS.json` SHA256 `7931e9a9854526d898e153feb723a785d433ab2fdd6192d8b96b6ada31b6a934`（本地与服务器一致）。
- 渲染函数与预登记的 `segment_sim.py` 相同（直接导入其 `render()`），tokenizer 与 `TokenizeManager` 来自 release-e2 worktree（只读，导入时使用 `-B`，没有写入 `__pycache__`）。
- 逐轮核对结果：
  - `prompt_tokens`：seed_real 为 87100、87328、87484、89295、90697、90940、93269、95352；T2 为 12443 … 21976。全部等于预登记。
  - `ids` 哈希（前 16 位）：全部等于预登记。
  - 切段与 cached：在 prod 与 off 两种策略下，用 `segment_sim.replay()` 复现，与预登记的 `on_segments` / `off_segments` / `cached` 全部相等。
- **跨轨迹复用核查**：seed_real 与 T2 的全部 96 组轮次对之间，最长共享前缀是 58 token，小于 64（页大小）。因此 T2 第 0 轮不可能复用 seed_real 留下的快照，预登记中 `cached = 0` 的前提成立。

## 3. H2 工装

文件（服务器与本地副本的 SHA 前 16 位一致）：

| 文件 | SHA256（前 16 位） | 作用 |
|---|---|---|
| `task_a_runner.py` | `f0210979b38721c1` | 请求计划、SSE 解析、Prefill 行解析、窗口编排、argv 门、W0 检查 |
| `stub_server.py` | `db91f99382a88c6e` | 桩服务（只用标准库，不加载模型） |
| `analyze_task_a.py` | `2bedfb5db2f772a1` | 按 §6 机械计算 G1–G5（P3 使用） |
| `test_task_a_runner.py` | `651589ccce5564eb` | 单元测试 18 项 |
| `freeze_inputs.py` | `bff19a97e5ab56bb` | H1 |
| `build_restore12.py` | `65527a88d4aeac26` | H3 |
| `make_rehearsal_report.py` | `c3e82fd95f7e891a` | H4 结果核对，写 REHEARSAL.json |
| `run_rehearsals.sh` | `e1b24438737bee87` | 四项反向对照的启动脚本 |

**单元测试**：18 项通过（`venv-eval` 的 pytest，`-p no:cacheprovider`）。覆盖：非空首分片判定；Prefill 行解析与只读新增字节；启动参数差异门（正反各一）；cached 提取；OOM 分支；超时；清理失败分支；ABBA 顺序固定；请求计划与输入改动检测；窗口时限；启动失败；请求错误与工装异常；环境变量清理。

**变异检查**（在临时副本上故意植入缺陷，确认测试会失败）：

| 植入的缺陷 | 失败的测试数 |
|---|---|
| 空 role 包计入首 token | 1 |
| B 臂漏掉 `--no-prefill-anchor-cut` | 2 |
| OOM 时停掉整个窗口 | 1 |

**与 `oh_window` 的关系**：只 import，不复制、不修改。`load_d07`、`idle`、`capture_birth`、`cleanup`、`compute_expected_argv` 直接使用。已在服务器上用 venv-eval 验证：导入 `oh_window`（其依赖 `hybrid_service`）与 `load_d07()` 成功，`CUDA_VISIBLE_DEVICES` 为空，没有取锁，`/data2/_shared/gpu.lock` 仍为生产持有。

**一处与指令不同的做法**：`oh_window.validate_argv_diff` 只允许 hybrid 与 `--moe-hybrid-max-fetch` 两类差异，会拒绝 `--no-prefill-anchor-cut`。因此 B 臂改用 `compute_expected_argv(..., {"type": "offload", "extra_argv": ["--no-prefill-anchor-cut"]})`，并在工装内用独立的 `verify_argv` 再核对一次。这一点已写入协调日志，请主会话确认。

**真实启动路径尚未在 GPU 上运行**：W4 的启动、等待健康、清理、GPU 锁这一段，P1 只能做到 import 与参数门，无法在不取锁、不碰生产的情况下运行。它在 P2 第一次执行，窗口开始前由 W0 与窗口前检查把关。

## 4. H3 恢复包 restore12

- 构建脚本：`build_restore12.py`，模板为 `restore10/`（只读复制，排除 `EXECUTION_TIME_PREFLIGHT.json`、`__pycache__`、`.pytest_cache`）。
- 替换：只替换两个精确字符串（`RESTORE481-MORNING-20261011-10` → `-12`，`ROLLBACK184-MORNING-20261011-10` → `-12`），共 11 处，位于 `DEPLOYMENT_APPROVAL.json`（5）、`ROOT_FINAL_REVIEW.json`（1）、`observe_overnight.py`（1）、`test_cpu_orchestration.py`（4）。
- 身份说明：`README.md` 与 `ROOT_FINAL_REVIEW.json` 的 `scope` 改写为 Restore12；`SOURCE_MANIFEST.json` 的 `package` 改为 `ophak_task_a_20261011/restore12`。
- 重算顺序：SOURCE_MANIFEST → DEPLOYMENT_APPROVAL（`package_source_manifest_sha256`）→ approval 的 SHA（`cd09c4bd4dee…`）→ ROOT_FINAL_REVIEW。manifest SHA `33d4756a058a…`。
- 验证：
  - `pytest test_cpu_orchestration.py`：**7 passed**；
  - 门链：`GATE_CHAIN_PASS RESTORE481-MORNING-20261011-12 2026-10-12T09:00:00+08:00`。
- **diff**（`diff_restore12.txt`，131 行，逐条核对）：只包含允许的类别：两处身份字符串、`run_dir`、三处重算的哈希、`README.md` 与 `scope` 的身份说明，以及模板中排除的两项（`Only in restore10`）。没有其它改动。
- `recorded_at` 沿用模板的 `2026-10-11T08:31:43.709991+08:00`（与 restore10 一致，未作为允许差异列出，门链不检查它）。

**需要主会话确认的一点**：`ROOT_FINAL_REVIEW.json` 的 `verdict: PASS` 与 `reviewer_role: root_independent_final_reviewer` 是执行者按 §H3 写入的。`deploy_conditional.require_root_final_review` **不校验** `independent_review_sha256` 指向的任何文件内容，所以门链本身不能证明有独立审查发生。真正的放行依据是主会话写"任务 A 放行"，W0 检查也以它为准。请主会话确认这样处理是否符合意图。

## 5. H4 演练结果

演练目录：`/data2/FreeToken/runs/dev_ophak_task_a_20261011/rehearsal/`。桩服务按预登记复现时序，**演练只证明工装的算术、切段比对与窗口编排路径，不是证据**。REHEARSAL.json 中的逐项结果以机械核对为准。

| 演练 | 配置 | 结果 | 关键证据 |
|---|---|---|---|
| **R1 正向对照** | 缩放 1.0，桩服务时序按预登记（单遍 2.7775 s） | PASS（20 项机械核对全部通过） | G2 中位数 2.780 s（区间 2.3–3.0），14 个会变轮的 Δ 最小 2.774 s；阴性对照中位数绝对值 0.001 s；同臂漂移最大 0.28%；冷轮 seed Δ 0.00 s（预测区间 [-0.5, 1.5]），T2 Δ 2.78 s（预测区间 [2.0, 3.0]）；绝对值全部在预登记带内；同臂输出逐字相同 |
| **R2a 反向 (a)：首分片为空 role 包** | 缩放 0.05 | PASS | seed_real/00 首 token 0.99 s，与预填时间 0.93 s 吻合；若把 role 包计入，首 token 会接近 0 |
| **R2b 反向 (b)：错误 cached** | A1_on 的 seed_real/02 返回 cached=0 | PASS | 只有 A1_on 的 seed_real/02 被标为复用不符（usage 与首条 Prefill 行都不符）；切段（G1）不受影响 |
| **R2c 反向 (c)：OOM** | B1_off 在 seed_real/03 注入 OOM | PASS | B1_off 在第 5 条中止，seed_real/03 只发送 1 次，之后没有任何请求；B2_off、A1_on、A2_on 完整跑完；OOM 摘录已写出 |
| R2d 反例（额外） | B2_off 的 seed_real/05 切段改为 [2000, 104] | PASS | G1 只在 B2_off 第 5 轮标为"模型在第 5 轮不成立"；工装没有因此停止 |

REHEARSAL.json 的 `all_pass` 为 true（五项演练，全部检查通过）。warmup 不计入 G 类判读。

**需要说明的局限**：R1 的 Δ 恰好等于桩服务按预登记模型给出的 2.7775 s，所以它只证明算术正确，不证明预测成立。预测是否成立只能由 P2 的真实窗口回答。

## 6. 需要主会话确认的事项（指令未覆盖，或与代码不一致）

1. **非 OOM 的请求错误**：指令 §5 没有对应行。工装的做法是：清场后停止整个窗口（`terminal=request_error`），481 不自动恢复，由主会话决定恢复还是诊断。请确认。
2. **漂移的相对差**：指令写"相差不超过 10%"，工装取 `|a − b| / max(a, b)`。请确认取法。
3. **W0 的 D11-P0 终态**：工装在协调日志中识别形如 `- <时间> Gemini|主会话 … D11-P0 … 测量完成|今日不测|取消|否决` 的行。当前 Gemini 的 D11-P0 尚未开始，所以 W0 会不通过，需要 Gemini 写终态行，或主会话写否决。
4. **本地 STOP 文件**：`plan/OPHAK_TASK_A_STOP.md` 只在服务器侧检查（工装无法看到办公电脑的文件），本地侧由操作者人工确认。
5. **B 臂冷 87K 单段**：推算余量约 0.3 GiB（指令 G5）。若 OOM，按 §5 中止该服务，不重试；OOM 的时刻与摘录会写入 `oom_excerpt.log`。
6. **手动步骤**：W1 清场、W2 观察器停止、W3 停 481、W5 恢复按指令用命令逐步执行，没有写进工装。
7. **门链的 OOM 额度**：481 每个进程只有 1 次 OOM 自动恢复（`api_server.py:1234`）。窗口里的测试服务是新进程，各自有额度；生产的 W5 恢复会使用新进程，额度复位。

## 7. 证据索引

| 证据 | SHA256（前 16 位） |
|---|---|
| `INPUTS.json` | `7931e9a985452…` |
| `REHEARSAL.json`（0444） | `e8af4f6ae3bd146e…` |
| `diff_restore12.txt` | `faf51196efed3a08…` |
| `restore12/DEPLOYMENT_APPROVAL.json` | `cd09c4bd4dee…`（approval 的 SHA） |
| `restore12/SOURCE_MANIFEST.json` | `33d4756a058a…`（manifest 的 SHA） |
| `restore12/ROOT_FINAL_REVIEW.json` | `a05f4de8cad8…` |
| `task_a_runner.py` | `f0210979b38721c1…` |
| `stub_server.py` | `db91f99382a88c6e…` |
| `analyze_task_a.py` | `2bedfb5db2f772a1…` |
| `test_task_a_runner.py` | `651589ccce5564eb…` |

证据位置（服务器）：WORK 为 `/data2/FreeToken/development/ophak_task_a_20261011/`；演练输出为 `/data2/FreeToken/runs/dev_ophak_task_a_20261011/rehearsal/`。本地镜像含 `inputs/`、`INPUTS.json`、`restore12/`、`diff_restore12.txt`、全部工装文件与本文件。
