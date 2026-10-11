# Gemini 指令：D09 启用路径——正确性（T17）与收益 A/B（2026-10-11 晚，主会话）

> 读者是执行者。请**从头读到尾再动手**。遇到本文没写到的情况，就停下，在协调日志写明原因，等主会话处理。
>
> **本文件发出后冻结，不再修改。** restore11 的独审字段与 T17 准入文件都绑定本文件的 SHA256；如需更正，主会话会另发补充文件。
>
> 上一份指令 `plan/GEMINI_OOM_HYBRID_20261011.md` 中的环境、红线、日志格式依然适用，本文 §0 再完整列一次。

---

## 0. 角色、环境与红线

### 0.1 角色

- **你**：执行者。负责改写测试工装、在 CPU 上演练、执行 GPU 窗口、写报告。
- **主会话**：审核者。负责写指令、复核结果。
- **用户**：拍板人。

**用户授权（2026-10-11 19:00 前后）：** 下一个 GPU 窗口只做 D09 启用路径。目的是拿到论文中第一项"本文机制、实测收益"（见 `plan/PAPER_BENEFIT_LEDGER_20261011.md`）。

### 0.2 环境

| 项 | 值 |
|---|---|
| 测试服务器 | `172.16.108.9`。从办公电脑用 `ssh 9 '<命令>'` 执行，登录用户 dell |
| 本地仓库 LOCAL | `D:\00.开发\2026\03-模型实验\freetoken\freetoken\` |
| 服务器目录 SRV | `/data2/FreeToken/` |
| Python | 引擎与工装用 `/data2/FreeToken/venv/bin/python` |
| D09 候选 | `7d8d389ee5d85de7e4f8e533f35c27f4c4c02690`（D09fix），工作树 `SRV/wt/d09_fix_20261011`（只读）。它是发布版 481d3a7 的后代：13 个提交，16 个文件 |
| D09 开关 | 命令行 `--enable-message-boundary-ckpt`，默认关闭 |
| 生产服务 | 481，监听 `172.16.108.9:8095`。当前审批号 `RESTORE481-MORNING-20261011-10`，恢复包 `SRV/development/gemini_oom_hybrid_20261011/restore10/`；观察器 pid 2635719，运行到 2026-10-12 09:00 |

### 0.3 产出位置

| 用途 | 服务器 | 本地镜像 |
|---|---|---|
| 代码、文档（下称 WORK） | `SRV/development/gemini_d09_enable_20261011/` | `LOCAL/development/gemini_d09_enable_20261011/` |
| B 运行输出（下称 RUNS） | `SRV/runs/dev_gemini_d09_enable_20261011/` | 不必镜像 |
| T17 运行输出 | 由 T17 runner 自己决定，在 `WORK/t17/runs/` 下 | 不必镜像 |

### 0.4 红线

1. 不推送代码，不启动 Ollama，不改论文。
2. 不修改以下内容，只允许 `import` 或调用：候选工作树、发布版工作树、模型目录、他人的工装与证据目录、`/data2/_shared/runs/ft_rounds/` 下已有的文件。
   - 例外：W3 的结案脚本按 b163 的同一流程**新增**结案文件，这是唯一允许写入的地方：
     - b167 目录中的 `closure_evidence/`、`round.json`、`MANIFEST.sha256`、`round_history/`、`round_json_append.py`；
     - `SRV/runs/plan_batches/closed_round_pins/E2-D09FIX-T16-20261011.json`。
3. 不手动删 `/data2/_shared/gpu.lock`；不用 kill 结束不属于你的进程。停生产只能用 §4 W2 的命令。
4. 任何一步失败都**不重试**，按 §5 的失败路由处理。
5. 不把用户的邮箱或任何个人信息发给任何服务。
6. 在 Windows 上写要拷到服务器的文件时，一律用 LF 换行。写中文文件后，用 `open(f,'rb').read().decode('utf-8')` 自检编码。上一份指令中，`OOM_MEMORY_MODEL.md` 有 196 处 UTF-8 损坏。

### 0.5 协调日志

每完成一步，在 `LOCAL/plan/COORDINATION_LOG.md` 末尾追加一行，然后同步到 `SRV/plan/`：

```
- <时间戳> Gemini：<步骤号> <结果>（附关键 SHA256 前 12 位）
```

时间戳一律用服务器的真实时间：`ssh 9 'date "+%Y-%m-%dT%H:%M:%S+08:00"'`。

---

## 1. 背景

### 1.1 D09 是什么

D09 是 M1 的第二步：消息边界检查点。

适用场景：Agent 客户端改写了历史中的某条消息，例如截断工具输出。这时，新请求与上一轮只在"被改消息之前的那个消息边界"之前相同。

- **不开 D09：** 前缀缓存只能复用到页边界（64 的倍数），本例为 20,160。
  - 剩下的部分要分**两段**预填：20,160 → 20,282，然后 20,282 → 结尾。
  - 每段都要把专家整体流一遍。生产配置下一遍约 2.78 s（b167 的 `PARENT_b167/tax.json`，单遍中位数 2.7775 s）。
- **开 D09：** 在边界 20,282 处存精确检查点，续算从 20,282 开始，只需**一段**。

**CPU 证据（已有）：**
- `development/d09_fix_20261011/D09_ACTUAL_BD57_V7_ONE_PAGE.md`：用真实的调度器和缓存管理器回放，开启时复用 20,282，关闭时复用 20,160；"续算前向次数 2 → 1"。
- 预登记时，5 轮中有 2 轮受影响。

### 1.2 现状

| 项 | 状态 |
|---|---|
| 旧候选 bd57 的 T17（b164） | failed_harness：热目标请求报 `cached_tokens=20160`，预期 20,282（`protocol_t17/runner.py:166` 的断言）。独立结案审查判定这是产品行为不符，不是工装问题。D09fix 正是为修这一点 |
| D09fix 的 T16 默认门（b167） | 测量 kept（8 个服务、100 次调用，默认关闭时与 481 逐位相同），**但没有正式结案**：`/data2/_shared/runs/ft_rounds/E2-D09FIX-T16-20261011/` 下没有 `round.json` 和 `MANIFEST.sha256`。T17 runner 的准入要求 T16 已正式结案 |
| b167 独立审查 | **主会话已完成并封存**：`SRV/plan/reviews/d09fix_b167/INDEPENDENT_REVIEW_b167.json`，SHA256 `8708b545dc0a1d736c31cb61f2e3d447ac5ea5c6ecb76e87455f68778d5e8177`，0444，verdict PASS，11 项检查全过。生成脚本在同目录 `make_b167_review.py`（`18e90dae…`） |
| 收益 | 从未测过 |

### 1.3 本次要回答的两个问题

1. **T17（正确性）：** D09fix 开启时，在 GPU 上能否建立 20,282 / 22,558 的精确入口，且续算与同结构冷参照逐位一致？
2. **B（收益）：** 同一候选、同一参数，只差 D09 开关时，受影响轮次的预填段数是否从 2 降到 1、耗时是否少约一遍？

**测试格子：** 两题都用同一组冻结输入 `D09_T17_EXACT_INPUTS.json`（`inputs_sha256 = b21a29e4…`），共两个格子：

| 格子 | 来源 | 边界 | 尾段 | 提示长度 | 常规页下限 |
|---|---|---|---|---|---|
| c0 | 第 7 轮 | 20,282 | 1,020 | 21,302 | 20,224 |
| c1 | 第 10 轮 | 22,558 | 197 | 22,755 | 22,528 |

每个格子都有 donor（上一轮）与 target（改写后的本轮）两段 token 序列，前缀相同，到边界 + 1 为止。

---

## 2. 总览与时间

| 阶段 | 内容 | 占 GPU / 停 481 | 预计 |
|---|---|---|---|
| P1-H1 | b167 结案脚本 | 否 | 20 分钟 |
| P1-H2 | T17 runner 改写到 D09fix + 准入生成脚本 | 否 | 30 分钟 |
| P1-H3 | B runner（收益 A/B） | 否 | 45 分钟 |
| P1-H4 | restore11 | 否 | 20 分钟 |
| P1-H5 | 真实入口演练（含反向对照） | 否 | 30 分钟 |
| P1-H6 | 就绪记录 | 否 | — |
| P2 | GPU 窗口：结案 → T17 六个服务 → B 四个服务 → 恢复 | **是** | 约 65 分钟，上限 120 分钟 |
| P3 | 报告 | 否 | 20 分钟 |

---

## 3. P1：纯 CPU 准备（481 继续服务）

### P1-H1 b167 结案脚本（交付 `WORK/close_t16_batch167.py`）

1. 按字节复制 `SRV/development/d09_gpu_reapplication_20261010/close_t16_batch163.py`。
2. **只做以下替换**，每一处都写进 `WORK/diff_close167.txt`（`diff -u`）：

| 原文 | 改为 |
|---|---|
| `RID = 'E2-D09-T16-reapply-bd57-20261010'` | `RID = 'E2-D09FIX-T16-20261011'` |
| `BATCH = 163` | `BATCH = 167` |
| `CANDIDATE = 'bd57cfdccc2a935d46cb0a89b8b36be7a18706de'` | `CANDIDATE = '7d8d389ee5d85de7e4f8e533f35c27f4c4c02690'` |
| `n + '_b163'` | `n + '_b167'` |
| `status_batch163.json`、`gate_batch163.json`、`tools_batch163.json`（各处） | 163 → 167 |
| `f'launch_{RID}_batch163.json'` | `f'launch_{RID}_batch167.json'` |
| `'/data2/_shared/runs/ft_rounds/batch163.log'` | `…/batch167.log`（该文件已存在，9,897 字节） |
| `'close_t16_batch163.py'`（复制进 closure_evidence 的文件名） | `'close_t16_batch167.py'` |
| `'card': 'D09-T16'` | `'card': 'D09FIX-T16'` |
| reason 字符串中的 `bd57 default-off` | `D09FIX 7d8d389e default-off` |
| `HERE / 'protocol_t16/d07_g3g4_prepare.py'` | `Path('/data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/d07_g3g4_prepare.py')`。两份文件 SHA 相同，都是 `c4a28aaa…` |

3. **只新增一个参数 `--validate-only`。** 它调用 `validate()`，但跳过 GPU 空闲与锁这一项检查，在输出中注明"GPU check skipped"，并且不写任何文件。`--execute` 路径与 b163 完全相同（只差上表的身份字段）。
4. **CPU 自检：**
   - `python -B close_t16_batch167.py --validate-only --independent-review /data2/FreeToken/plan/reviews/d09fix_b167/INDEPENDENT_REVIEW_b167.json` 必须通过。也就是说，独审的绑定、原始文件 SHA 映射（160 个文件）、启动回执、8 个服务的所有权清理、调用数（12/13，共 100）、两个工具的 SHA（`fd3d40c2…`、`67c36b2f…`）都成立。
   - 反向对照：把独审文件复制一份、把 `batch` 改成 166 并设为 0444，用它跑 `--validate-only`，必须报 "independent review binding differs"。

### P1-H2 T17 runner 改写（交付 `WORK/t17/`、`WORK/make_t17_admission.py`）

1. 按字节复制 `SRV/development/d09_gpu_reapplication_20261010/protocol_t17/` 中的以下文件到 `WORK/t17/`：
   - `runner.py`；
   - `D09_T17_EXACT_INPUTS.json`；
   - `tooling/` 下的 `t17_d14_exact_ids.py`、`t17_d14_observe.py`、`t17_d14_startup.py`。

   不复制 `runs/`、`evidence_*`、`__pycache__`。
2. **只做以下身份替换**，每一处都写进 `WORK/diff_t17.txt`：

| 行（原文件） | 原文 | 改为 |
|---|---|---|
| 7 | `RID='E2-D09-T17-reapply-bd57-20261010'` | `RID='E2-D09FIX-T17-20261011'` |
| 8 | `PROVENANCE=HERE.parent/'protocol_t16/d09_native_provenance_bd57.json'` | `PROVENANCE=Path('/data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/d09fix_native_provenance_7d8d389e.json')` |
| 9 | `WT=ROOT/'wt/d09-page-conservation-20261010'`；`CANDIDATE='bd57…'` | `WT=ROOT/'wt/d09_fix_20261011'`；`CANDIDATE='7d8d389ee5d85de7e4f8e533f35c27f4c4c02690'` |
| 23、42 | `'aaf7a1d1ee3f329affb1458da917bc689e05c01fbda53dcaaa9ed42fe747c18f'` | `'6d9de3232c799777caaa6f4ec9104911f64740a5653ead894c5c811f96500f7c'`（D09fix 原生扩展记录的 SHA） |
| 96 | `closure['rid']!='E2-D09-T16-reapply-bd57-20261010'` 及其报错文字 | `'E2-D09FIX-T16-20261011'` |
| 269、294 | filedry 里的 `'E2-D09-T16-reapply-bd57-20261010'` | `'E2-D09FIX-T16-20261011'` |

   - 改完后执行 `grep -n "bd57\|aaf7a1d1\|protocol_t16\|reapply" WORK/t17/runner.py`，结果必须为空。若还有命中，停下回报。
   - **不改任何判据或流程代码**，包括 `evaluate()`、`judge_boundary()`、`child()` 和端口。
3. **CPU 验证**（`CUDA_VISIBLE_DEVICES=`）：
   1. `python -B -c "import sys; sys.path.insert(0,'.'); import runner; print(runner.validate_candidate())"` 必须通过：候选 HEAD 正确、工作树干净、源码中有开关、两个 `.so` 的 SHA 和大小与记录相符。
   2. `python -B runner.py --filedry` 必须通过（即 `filedry_v6_e2e`，6 个服务、8 次调用的假路径）。
   3. 反向对照：在 Python 中调用 `runner.filedry_v6_e2e(name='evidence_cpu_filedry_negative', fail_rebind=True)`，必须以端口重绑失败结束，不能报通过。
   4. 反向对照：复制一份 runner，把第 23 行的 SHA 改错一位，`cfg()` 必须断言失败。
4. **准入生成脚本** `WORK/make_t17_admission.py`：在窗口中、b167 结案之后运行。
   - 读取 `/data2/_shared/runs/ft_rounds/E2-D09FIX-T16-20261011/round.json` 与 `MANIFEST.sha256` 的 SHA256；
   - 用 `runner.cfg()` 取得 `inputs_sha256`、`runner_sha256`、`tooling_sha256`；
   - 以 `x` 模式写 `WORK/t17_admission.json`，设为 0444。内容：

```json
{
  "root_approved": true,
  "rid": "E2-D09FIX-T17-20261011",
  "candidate": "7d8d389ee5d85de7e4f8e533f35c27f4c4c02690",
  "inputs_sha256": "<cfg()>",
  "runner_sha256": "<cfg()>",
  "tooling_sha256": "<cfg()>",
  "required_gates": {"T16": "passed"},
  "t16_closure": {"rid": "E2-D09FIX-T16-20261011", "verdict": "kept", "round_json_sha256": "<实算>", "manifest_sha256": "<实算>"},
  "authorized_by": {"directive": "plan/GEMINI_D09_ENABLE_20261011.md", "directive_sha256": "<本文件 SHA256>"},
  "services_max": 6,
  "generation_calls_max": 8,
  "push_approved": false
}
```

   - 写完后立即调用以下两项，都必须通过；任何一项失败，脚本以非零码退出：
     - `runner.check_admission(Path(adm), runner.cfg(), runner.d07())`：用真实的 d07 模块重新核对 T16 结案；
     - `runner.validate_candidate()`：核对候选 HEAD、干净度、开关与原生扩展。
   - CPU 演练时（closure 尚不存在），在临时目录用假的 `round.json` 和 `MANIFEST` 生成准入，再以 `g=None` 调用 `check_admission`，必须通过。反向对照：把 rid 改错，必须被拒绝。

### P1-H3 B runner：收益 A/B（交付 `WORK/b_runner.py`、`WORK/test_b_runner.py`、`WORK/stub_exact_ids.py`）

**原则：** 以 `import` 方式复用 `WORK/t17/runner.py` 的函数，不复制、不修改。用到的有：`cfg`、`arm_files`、`reserve_pair`、`release_pair`、`ROW`、`put`、`sha`、`wait_gpu_idle`、`d07`。

#### 服务（顺序固定，ABBA）

| 序 | 名称 | 格子 | D09 | 端口对 |
|---|---|---|---|---|
| B1 | `off_c0` | c0 | 关 | 31521, 31522 |
| B2 | `on_c0` | c0 | 开 | 31523, 31524 |
| B3 | `on_c1` | c1 | 开 | 31525, 31526 |
| B4 | `off_c1` | c1 | 关 | 31527, 31528 |

#### argv

- 取 `runner.cfg()` 中对应格子的 `hot` 服务 argv，做以下改动：
  1. 把 `--port <api>` 换成上表的 api 端口；
  2. argv 中以 `t17_d14_startup.py` 结尾的那一项，原本指向 T17 自己的 arm 目录，换成 `<B 的 arm>/t17_d14_startup.py`；
  3. **D09 关闭的服务，删掉 `--enable-message-boundary-ckpt` 这一项。**
- 其余逐项不变。
- 每个服务写 `argv_diff.json`，记录与 T17 hot argv 的差异。只允许以上三类差异，出现其他任何差异，拒绝启动。
- `arm` 目录设为 `RUNS/<out>/<名称>`。
  - 调用 `runner.arm_files(s, c)` 时，传入 B 自己构造的服务字典（其中 `arm` 指向 B 的目录），由它复制启动包装文件并校验 SHA。
  - **不要在 T17 的 RUNROOT 下创建任何目录。**

#### 环境变量

与 T17 child 逐项相同：

```
env = g.clean_environment(WT)
env.update(PYTHONPATH=str(WT/'python'),
           FT_T17_INPUT_RECEIPTS=str(arm/'input_receipts'),
           FT_T17_OBSERVATIONS=str(arm/'observations.jsonl'),
           FT_DEV_STATE_DUMP=str(arm/'state_dump'),
           FT_T17_ARM_SOURCE='hot')
```

开、关两臂的埋点完全相同，所以埋点开销对两臂对称。

#### 每个服务的生命周期

与 T17 child 相同：

1. 端口探测（`reserve_pair` 后立即 `release_pair`）；
2. `Popen(argv, cwd=arm, env=env, stdout=serve.log, stderr=STDOUT, start_new_session=True)`，写 `pid_birth.json`（`g.process_identity`）；
3. 每 2 秒轮询 `/health`，直到 `status=="ok"`，上限 600 秒；
4. 依次发 donor、target 两次请求（见下）；
5. `g.load_owned_lifecycle().stop_owned_process(proc,120,30)`，然后确认 `owned_group_alive` 为假；`wait_gpu_idle(g)`；端口重绑，写 `cleanup.json`。

**GPU 锁：**
- B 整体只取一次锁：`owner = g.take_d07_gpu_lock('GEMINI-D09-BENEFIT-20261011', 0)`。四个服务结束后 `g.release_d07_gpu_lock(owner)`。
- 清理失败时保留锁，写 `CLEANUP_BLOCKED.md`，中止 B（同上一份指令的规则）。

#### 请求

- POST `http://127.0.0.1:<api>/internal/t17/exact-ids`，body 为 `{"input_ids": <ids>, "max_tokens": 32}`，与 T17 runner 第 350 行相同，超时 600 秒。
- 每次调用记录：
  - 发送前、收到后的 `time.monotonic()`，以及差值 `wall_s`；
  - 响应原文（`call_<n>.response.json`）和其中的 `usage`；
  - 这次调用期间 serve.log 新增内容中，所有匹配 `runner.ROW` 的行。每行解析出 `#new-seq`、`#new-token`、`#cached-token`；
  - 输出文本的 SHA256。
- 结果写 `RUNS/<out>/b_results.json`。

#### 时限与终态

- B 总时限 40 分钟。超时后不再启动新服务，已启动的服务正常清理。
- 每个服务写 `terminal.json`，总控写 `summary.json`。
- **B 只测量，不做任何判定。** 判读按 §6 由报告完成。

#### 单元测试 `test_b_runner.py`

至少覆盖：
- argv 差异门：只允许端口与开关；
- ROW 解析：含两行的窗口；
- 时间与差值计算；
- ABBA 顺序固定；
- 超时逻辑。

#### 桩服务 `stub_exact_ids.py`

只用标准库。提供：
- `/health`；
- `/internal/t17/exact-ids`：按配置返回 `usage`，并向 stdout 打印与真实格式相同的 `Prefill batch, #new-seq: 1, #new-token: X, #cached-token: Y, …` 行，每行之前 `sleep(pass_seconds)`。

可配置项：
- 每格开、关两种模式下的行数与 cached 值；
- `pass_seconds`。

### P1-H4 restore11（交付 `WORK/restore11/`、`WORK/diff_restore11.txt`）

做法与上一份指令的 P1-G4 完全相同，模板换成 `SRV/development/gemini_oom_hybrid_20261011/restore10/`：

1. `cp -a`，然后删除复制过来的 `EXECUTION_TIME_PREFLIGHT.json`、`__pycache__`、`.pytest_cache`。
2. **只替换两个精确字符串：**
   - `RESTORE481-MORNING-20261011-10` → `RESTORE481-MORNING-20261011-11`；
   - `ROLLBACK184-MORNING-20261011-10` → `ROLLBACK184-MORNING-20261011-11`。

   `run_dir` 随之变为 `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11`，该目录事先必须不存在。`observation_until` 不变，仍为 `2026-10-12T09:00:00+08:00`。
3. **按顺序重算：**
   1. `SOURCE_MANIFEST.json`；
   2. `DEPLOYMENT_APPROVAL.json` 的 `package_source_manifest_sha256`；
   3. 审批文件的 SHA；
   4. `ROOT_FINAL_REVIEW.json`：
      - `independent_review_sha256` = **本文件**的 SHA256；
      - `scope` 写为 "Identity-only Restore11 (Gemini D09 window copy of Restore10)…"；
      - README 的身份说明同步修改。
4. **验证：**
   - pytest：7 passed；
   - 门链打印 `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-11 2026-10-12T09:00:00+08:00`；
   - `diff -ru restore10 restore11` 中只出现允许的类别。出现其他差异，就判 H4 失败，**今晚窗口取消**。
5. 全部文件设为 0444。

### P1-H5 真实入口演练（交付 `WORK/REHEARSAL.json`，0444）

**演练里只允许替换以下四项**，其余全部走真实代码：

1. GPU 锁的取与放；
2. `require_gpu_idle` / `wait_gpu_idle` 改为空操作并记录调用；
3. 服务 argv 换成桩服务；
4. 跳过"生产已停"的前置检查。

参照上一份指令的经验，**要替换的是模块属性本身**（d07 对象上的方法），只改局部引用不够。`process_identity`、`load_owned_lifecycle`、`clean_environment` 保留真实实现。

| 演练 | 内容 | 必须得到的结果 |
|---|---|---|
| R1 | B 正向。桩：关闭时 2 行（c0 的 cached 为 20160，c1 为 22528），开启时 1 行（cached 为边界值）；`pass_seconds=2.8` | 4 个服务走完；`b_results.json` 中每格关闭的 target 有 2 行、开启的有 1 行；`wall_off − wall_on` ≈ 2.8 s（±0.5）；argv_diff 只含允许的差异 |
| R2 | B 反向。桩：开启时也打 2 行、cached 为 20160（模拟 D09 未生效） | 按 §6.2 的规则，判读脚本得出"D09 未生效 / 无收益" |
| R3 | 清理 | 每个服务结束后，桩进程组全部消失，端口可重绑 |
| R4 | T17 filedry 正向与反向（H2-3 的 ii、iii） | 正向通过；fail_rebind 失败 |
| R5 | 结案脚本 `--validate-only`，以及错误独审的反向对照（H1-4） | 正向通过（只跳过 GPU 检查）；反向被拒 |
| R6 | 准入脚本：假结案正向，错 rid 反向（H2-4） | 正向通过；反向被拒 |

`REHEARSAL.json` 记录 R1–R6 的命令、结果，以及全部源文件的 SHA256。任何一项不符就改，改后全部重跑。

**判读脚本：** §6.2 的判读规则要写成代码，即 `WORK/b_judge.py`，读 `b_results.json`、输出判读。R1、R2 都要经过它，确保规则本身能区分正反两种情况。

### P1-H6 就绪记录

写 `WORK/CPU_READINESS.md`，包括：
- H1–H5 的交付清单与 SHA256；
- pytest 输出；
- 三份 diff；
- `t17_admission.json` 的模板；
- `b_results` 的字段说明。

然后在协调日志写"Gemini：D09 P1 就绪"。

---

## 4. P2：GPU 窗口

### W0 开窗条件（全部满足才开）

1. 协调日志已有"Gemini：D09 P1 就绪"。
2. 本地与服务器的 `plan/GEMINI_STOP.md` 都不存在。主会话复核 P1 时如发现问题，会写这个文件。
3. **不与 Codex 冲突：**
   - `pgrep -f stall_probe.py` 为空，且 `SRV/runs/dev_d11_p0_20261011/` 在最近 10 分钟内没有文件更新（目录不存在也算满足）；
   - 如果 Codex 正在测量，等它结束，最多等 45 分钟。超过 45 分钟，写"D09 窗口与 D11-P0 冲突"，等主会话。
   - **没有钟点限制**，不必等到某个时刻。
4. `env | grep -E "^(FREETOKEN_|FT_)" | wc -l` 为 0。
5. 生产 -10 在服务：`/health` 返回 serving，`/data2/FreeToken/run/production.active.json` 的 `approval_id` 为 -10。

### W1 提前结束 -10 观察器

步骤同上一份指令 §5.2：

1. `start.json` 位于 `SRV/runs/production/RESTORE481-MORNING-20261011-10/overnight_observation/start.json`，当前 `observer_pid` 为 2635719。
2. 核对父进程 `post_night_observer.py` 与进程组。
3. 用 `restore10/observe_overnight.py` 的 `eligible()` 检查全部样本是否健康。
4. 执行 `kill -TERM -<进程组号>`。
5. 写 `WORK/evening/OBSERVER_EARLY_STOP.json`，原因写"用户批准的 D09 窗口"。

身份核对不符就不杀进程，停下回报。

### W2 停 481

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10 && /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```

成功判据：
- 退出码 0；
- `SRV/runs/production/RESTORE481-MORNING-20261011-10/stopped.json` 存在；
- `SRV/run/production.active.json` 不存在；
- `gpu.lock` 不存在；
- `nvidia-smi --query-compute-apps=pid --format=csv,noheader` 为空。

### W3 b167 正式结案

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B close_t16_batch167.py --execute --independent-review /data2/FreeToken/plan/reviews/d09fix_b167/INDEPENDENT_REVIEW_b167.json'
```

- 成功时打印 `{"rid": "E2-D09FIX-T16-20261011", "verdict": "kept", "round_json_sha256": …, "manifest_sha256": …}`。记下这两个 SHA。
- 失败：**不做 T17**，跳到 W6，B 照做。

### W4 生成 T17 准入，并做真实核对

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B make_t17_admission.py'
```

- 脚本内已调用真实 d07 的 `check_admission`，加上 `validate_candidate()`，都必须通过。
- 失败：**不做 T17**，跳到 W6。

### W5 T17

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011/t17 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B runner.py --run --admission /data2/FreeToken/development/gemini_d09_enable_20261011/t17_admission.json'
```

- 这是 controller。它分配批号（预计 169），拉起托管子进程后返回。
- 记下 `WORK/t17/runs/launch_E2-D09FIX-T17-20261011_batch<N>.json` 中子进程的身份。
- **等待：** 每 30 秒检查一次 `WORK/t17/runs/E2-D09FIX-T17-20261011_batch<N>/E2-D09FIX-T17-20261011/terminal.json` 是否出现、子进程是否退出、`gpu.lock` 是否消失。三项都满足才进入 W6。
- **上限 75 分钟。** 超时后：
  - 先写 `WORK/T17_STALLED.md`；
  - 如果子进程仍存活、且 15 分钟内 serve.log 没有新增，可以对**该子进程组**执行 `kill -TERM`，这是你自己启动的进程；
  - 等 120 秒，锁仍不释放，就按"清理失败"处理（§5）。
- **T17 的结果不影响 B。** 无论 kept、not_met 还是 failed_harness，都继续 W6。

### W6 B

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B b_runner.py --execute --out /data2/FreeToken/runs/dev_gemini_d09_enable_20261011/b01'
```

上限 40 分钟。

### W7 用 restore11 恢复 481（三步，不要用 `deploy_conditional.py --execute`）

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011/restore11 && /data2/FreeToken/venv/bin/python start_approved_release.py'
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011/restore11 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py'
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011/restore11 && setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11/observer_outer.log 2>&1'
```

成功判据与上一份指令 §5.5 相同：
1. 第一步退出码 0；
2. 冒烟回执 `exit_code=0`、`classification=passed`，与 df77cb 基准逐字段一致；
3. `/health` 返回 serving，`backend_epoch=0`；
4. 观察器的 `start.json` 已写出。

任一步失败就走回滚：

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d09_enable_20261011/restore11 && /data2/FreeToken/venv/bin/python -c "import subprocess; from deploy_conditional import recover_after_restore_failure; raise SystemExit(recover_after_restore_failure(subprocess.run))"'
```

回滚也失败：写 `WORK/PRODUCTION_DOWN.md`，并在协调日志标"紧急"。

---

## 5. 失败路由（所有步骤都不重试）

| 情况 | 处理 |
|---|---|
| W0 不满足 | 不开窗 |
| W1 失败 | 不停 481，回报 |
| W2 失败，481 仍在服务 | 不恢复，回报 |
| W2 失败，481 状态不明 | 走 W7 |
| W3 或 W4 失败 | 跳过 W5，做 W6，再做 W7 |
| W5：T17 判 not_met 或 failed_harness | 照常做 W6、W7 |
| W5 或 W6：清理失败、GPU 锁未释放 | 窗口中止。轮询 120 秒；仍未释放，写 `CLEANUP_BLOCKED.md`，**不能**走 W7（GPU 被占着，恢复必然失败）。在协调日志标"紧急"，等主会话 |
| 窗口总时长超过 120 分钟 | 不再启动新服务，当前服务清理后走 W7 |

---

## 6. 预登记的判读规则（窗口前写死，事后不改）

### 6.1 T17（正确性）

- 判读以 T17 runner 自己的 `terminal.json` 为准，规则见 `evaluate()` 与 `evaluate_cell()`：冷 A、冷 B 稳定；热与冷相等；边界状态相等；usage 契约成立。
- **预先说明归类：** 如果 terminal 的错误是 `evaluate()` 中 usage 断言失败，且热目标的 `cached_tokens` 不等于边界值（例如又是 20160），报告里要归为 **"not_met：D09fix 在 GPU 上没有建立精确入口"**，即产品行为不符。runner 本身会把它标成 failed_harness，这一点照实记录，但结论按产品行为写。b164 的结案审查就是这样处理的。
- 其他异常（启动、健康检查、端口、清理）归为 failed_harness。
- T17 的结果由主会话在窗口后做独立结案审查，Gemini 不写 `round.json`。

### 6.2 B（收益）

每个格子 X ∈ {c0, c1} 只看 target 调用：

| 项 | 预测 |
|---|---|
| 开启时 target 的 usage | `cached_tokens` = 边界（c0 为 20,282，c1 为 22,558）；`prompt_tokens` = 21,302 / 22,755；completion = 32 |
| 关闭时 target 的 usage | `cached_tokens` < 边界。b164 在 c0 上观察到 20,160；c1 如实记录 |
| 预填行数（ROW） | 关闭 2 行，开启 1 行 |
| Δ_X = wall(关闭 target) − wall(开启 target) | ≈ 一遍 ≈ 2.78 s |

**判读**（按顺序套用，先命中的为准）：

**先判 D09 是否生效。** "D09 生效"指：开启臂的 target 只有 1 行 ROW，且 `cached_tokens` 等于边界。

| 结果 | 读法 |
|---|---|
| 任一格的开启臂不满足"D09 生效" | **D09 未生效**（该格无收益可谈） |
| 两格都生效，且两格 Δ ≥ 2.0 s | **收益成立**：受影响轮次省一遍 |
| 两格都生效，但只有一格 Δ ≥ 2.0 s，或两格都在 0.5 ≤ Δ < 2.0 | **部分成立** |
| 两格都生效，但两格 Δ < 0.5 s | **生效但无时间收益**，须诊断 |

**关闭臂的行数是解释项，不是门槛。** 预测为 2 行。

- 若关闭臂实为 1 行，但 Δ ≥ 2.0 s，就写"收益成立，但预测的分段机制与观察不符，收益来源待诊断"。
- 若关闭臂为 2 行，而 Δ 远小于一遍，也要如实写出。

**参数说明：** B 与 T17 用的是 T17 协议的参数（`--kv-reserve-tokens 49152` 等），不是生产参数。论文换算收益时，用"省掉的段数 × 生产单遍 2.78 s"，B 的绝对秒数只作佐证。

**环境合理性检查：** 同一格开、关两臂的 donor 是同一次冷预填，耗时应在 ±10% 以内；超出就把 Δ 标为"仅供参考"。

**收益能否写进论文：** 只有 T17 判 kept（或主会话结案为 kept）时，B 的收益才能作为"本文机制、实测收益"写进论文。T17 不通过时，B 只作诊断数据。

**适用范围（如实写）：** 收益只发生在"客户端改写了历史消息"的轮次。本次预登记数据中 5 轮有 2 轮受影响，真实流量中的比例**未测**。

---

## 7. P3：报告 `WORK/RESULT.md`（0444）

内容包括：

- 每一步的终态和时刻；
- T17：terminal 原文的要点（每格的 cold_stable、hot_equals_cold、cached、边界状态），按 §6.1 归类；
- B：每格开、关两臂 target 的 usage、ROW 行、wall_s、Δ、donor 合理性检查，以及按 §6.2 的判读；
- 恢复冒烟结果；
- 全部证据的 SHA 索引；
- 与本指令不一致之处，**含任何 failed_harness 的根因**。必须打开原始记录查清，不能凭标志位推测。

**不许写本文没有的结论**，例如"完全无损""实际极限在 X–Y"之类没有数据支持的话。上一份报告有 5 处这类问题，见 `plan/GEMINI_OOM_HYBRID_REVIEW_20261011.md` §4。

然后在协调日志写"Gemini：D09 窗口结束，等主会话复核"。

---

## 8. 主会话下发前自检与反思

| # | 检查项 | 结论与依据 |
|---|---|---|
| 1 | 开关与语义已核实 | 候选源码 `server/args.py` 中有 `--enable-message-boundary-ckpt`，T17 runner 的 `validate_candidate()` 会实查；默认关闭，由 b167 默认门（逐位等同 481）证实 |
| 2 | 候选与发布版的关系 | `git merge-base --is-ancestor 481d3a70 7d8d389e` 成立；13 个提交、16 个文件；工作树干净（`status --porcelain` 为空） |
| 3 | 前置门 | T17 准入要求 T16 已正式结案。b167 只有状态文件、没有 round.json，这是本次发现的缺口。主会话已完成独审并封存（8708b545…，11 项全过）。结案脚本需要 GPU 空闲、没有锁，所以放在窗口里停服之后第一步，耗时几秒 |
| 4 | 真实入口 | T17 的 controller、子进程、d07 生命周期在 b164 真实跑过 3 个服务，本次只改身份字段。窗口里 W4 用真实 d07 核对准入与候选，作为最后一道廉价检查。B 复用同一套启动包装与清理函数 |
| 5 | 反向对照 | R2（D09 未生效能被识别）、R4（filedry 端口重绑失败）、R5（错误独审被拒）、R6（错 rid 被拒），外加 provenance SHA 错一位必须失败 |
| 6 | 基线对照臂（今天的第四次教训） | B 在同一窗口、同一候选、同一 argv 下设关闭臂，只差一个开关；ABBA 顺序 |
| 7 | 前缀缓存状态一致 | 开、关两臂都是同一序列："冷 donor → 热 target"；比较的都是 target |
| 8 | 埋点对称 | 两臂都用 T17 启动包装（含 `FT_DEV_STATE_DUMP`），开销对称；主判据是 ROW 行数与 cached（机制），时间差是次判据 |
| 9 | 论文已知限制 | §10.2"热请求可与普通冷请求不同"：T17 比较的是同结构冷参照（冷臂同样开启 D09），不与普通冷请求比较；B 不做文本相等判定 |
| 10 | 预测有出处 | 一遍 2.78 s 取自 b167 tax.json（生产参数）；"2 → 1"取自 CPU 真实调度回放；c0 关闭时 20,160 取自 b164 实测 |
| 11 | 时间安排 | 没有钟点限制；P1 约 2.5 小时；窗口约 65 分钟（6 + 4 个服务，每个加载约 4.5 分钟），上限 120 分钟。481 停服约 1–1.5 小时，属于停服窗口，主会话会事先告知用户 |
| 12 | 与其他指令冲突 | Codex D11-P0 的放行条件只认 -09 / -10。本次恢复后是 -11，主会话另发 Codex 补充 2，接受 -11。开窗只避让"正在进行"的测量，不再按钟点等 |
| 13 | 已知风险 | ① T17 若再次出现 cached 20160，说明修复在 GPU 上无效，预先归为产品 not_met；② B 的启动包装加关闭臂的组合未在 GPU 上跑过，但 argv 只少一个开关，b163/b167 的默认关闭路径已在 T16 上跑过；③ 结案脚本的 `--execute` 在 CPU 上无法完整演练（需要 GPU 空闲），已用 `--validate-only` 覆盖除 GPU 检查以外的全部校验 |
| 14 | 本次自省 | 起草过程中先后否定了两个方案：(a) 原想复用 10-09 的 T2 回放工具，核对后发现它绑定的是更早的候选 c17b69a4、从没上过 GPU，而且不测时间；(b) 原想用 `/v1/completions` 发 token 列表以避开启动包装，核对代码（`server/openai_api.py` 中 `handle_completion` 逐个元素当作提示）后发现不可行。两处都是先查代码再定方案 |
| 15 | 写完后的自查中发现并已改正 | (a) B 的 argv 取自 T17 的 `cfg()`，其中嵌着 T17 自己 arm 目录下的启动包装路径。原文只允许"端口与开关"两类差异，B 会因此拒绝启动，或误用 T17 的目录；已加为第三类允许差异，并禁止在 T17 的 RUNROOT 下建目录。(b) §6.2 判读表原来没有覆盖"关闭臂只有 1 行"的情形；已改为先判"D09 是否生效"，关闭臂行数只作解释项。(c) 准入脚本原来只写了 `check_admission`，已补 `validate_candidate()`。(d) 红线例外漏了结案时写入的 pin 文件，已补。(e) 已核对：按 H2 的替换表改完后，`grep "bd57\|aaf7a1d1\|protocol_t16\|reapply"` 在 runner 中确实为空（逐行比对过原文件第 7、8、9、23、42、96、269、294 行）；`D09_T17_EXACT_INPUTS.json` 两处副本的 SHA 都是 `b21a29e4…`；`d07.require_closed_round` 要求结案树全部只读、且有 pin，b163 的结案脚本两样都会写 |
