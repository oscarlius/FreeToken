# op-hak 任务 B：P1 就绪记录（CPU 阶段，2026-10-12 凌晨）

- 指令：`plan/OPHAK_TASK_B_CUT_POLICY_20261011.md`（SHA256 `64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186`）
- 预登记：`development/anchor_cut_accounting_20261011/PREREG_TASK_B_v2.json`（SHA256 `8df5ee4901795d287bed22cfaadbaef3515c89f530c4f9df26a5798489f9152d`）
- 执行者：op-hak；放行方：freetoken-06（主会话）
- 结论：**P1（CPU 阶段）完成。未开 GPU 窗口，未停 481。** 481 仍为 restore12（`RESTORE481-MORNING-20261011-12`）在服务，`/health` serving。GPU 窗口等主会话在协调日志写"任务 B 放行"，且 W0 全部通过之后才开。

## 1. 做了什么，没做什么

| 项 | 做了 | 没做 |
|---|---|---|
| 候选代码 | 核对提交 9db0ee77（diff 由主会话独立复核） | 没有 push；没有部署到生产 |
| 工装 | 构建门、参数门、死亡计数与停窗、启动路径的清场（见第 3 节） | 没有对生产发送请求 |
| 单测 | 33 项通过（venv-eval，`taskset -c 0,2`，`-p no:cacheprovider`） | — |
| 演练 | 8 组（正向 1 组 + 反向 7 组），桩服务，CPU，结果见第 5 节 | 演练不是证据，只核对工装路径 |
| restore13 | 由 restore12 模板构建；pytest 7 passed；门链 PASS；审批 user_authority 按主会话裁定改写（第 4 节） | 没有在生产上执行 |

资源：所有演练与单测只用核心 0、2；没有碰 8095；没有占 GPU（桩服务不加载模型，构建门探针在 `CUDA_VISIBLE_DEVICES` 为空时导入 freetoken）。

## 2. 候选代码（只在本地）

- 分支 `m1/cut-min-tokens`，提交 `9db0ee776c25afa8d2719ab700b2de7ccc606142`（"feat: add --prefill-anchor-cut-min-tokens (default 0)"）。无上游；远端无 `m1*` 引用；`git status --porcelain --untracked-files=no` 为空。
- 扩展 `.so` 为指向 release-e2 的符号链接，SHA256 前 16 位：`_cpu_moe` 10a2bd8311b9569b、`_pinned_tensor` 07701be28030c4eb，与指令常量前缀一致。
- 测试基线（提交说明）：`tests/scheduler` 在 481d3a7 为 137 passed / 6 failed；在 9db0ee77 为 145 passed / 6 failed，失败项相同（既有，非本次引入）。
- 离线切段核对（`offline_release.json`、`offline_candidate.json`，`all_match` 均为 true）：release N=0 的 20 轮与预登记 `on_segments` 相同；候选 N=0 的 20 轮与 `on_segments` 相同；候选 N=32768 的 20 轮与 `thresh_segments` 相同。

## 3. 工装（相对 A2 的 `task_a_runner.py`，SHA256 前缀 112917c56034）

- **构建门**（`check_build`）：用 `/data2/FreeToken/venv/bin/python3` 与服务自己的 `PYTHONPATH` 导入 `freetoken.scheduler.prefill`，实际路径必须在该构建根目录之下；结果写 `build_gate.json`（通过与否都写）；不通过 → `build_gate_refused`，停窗。候选 `PYTHONPATH` = `/data2/FreeToken/wt/m1-cutmin-20261011/python`，release = `/data2/FreeToken/wt/release-e2/python`。
- **参数门**（`param_gate`）：服务就绪后读 serve.log 中 `Parsed arguments:` 紧随的那一行（单行 `ServerArgs(...)` repr）里的 `prefill_anchor_cut_min_tokens`。release 应不存在该字段；候选 on 臂为 0，thresh 臂为 32768。结果写 `param_gate.json`；不通过 → `param_gate_refused`，停窗。该格式已对照生产 serve.log（restore12 的运行目录）核对：标题行后紧跟单行 repr。
- **死亡计数**（freetoken-06 裁定，已实现并演练）：`oom`、`worker_exit`、`launch_failed`（含没到 ready 就退出，或超时未就绪）**合并计数**。第一次：关掉该服务，继续下一个，并记录类型；同一窗口**累计第二次：立即停窗**（`second_death_stop`），按 W5 恢复 481。构建门、参数门、请求错误、清理失败、工装异常不计死亡，直接停窗。
- **启动路径**：进程先退出时 `wait_ready` 立即返回，不再等满 600 秒；清场抛异常记为 `cleanup_blocked`，不穿过窗口编排；真实路径取进程身份失败时只关本次子进程、释放 GPU 锁，计为启动失败。
- **服务表**（固定）：R0（release，on）→ C_A1（候选，on）→ C_B1（候选，thresh）→ C_B2（候选，thresh）→ C_A2（候选，on）；总时限 3600 秒，保留 480 秒。
- 轨迹与输入：warmup + seed_real 第 0–7 轮 + T2 第 0–11 轮（与任务 A 相同的 20 个 payload，`INPUTS.json` SHA256 `7931e9a9…`）。

## 4. restore13

- 由 `build_restore13.py`（SHA256 前 12 位 `ee103bf215e8`）以 restore12 为模板构建。模板的 SOURCE_MANIFEST 12 个文件逐一校验通过。
- 只替换两个精确字符串（`-12 → -13`，审批号与回滚号）。替换计数：DEPLOYMENT_APPROVAL.json 5、ROOT_FINAL_REVIEW.json 1、observe_overnight.py 1、test_cpu_orchestration.py 4。
- **未复制 `EXECUTION_TIME_PREFLIGHT.json`**（构建后确认不存在）。全部文件 0444。
- `run_dir` = `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-13`（未创建）。
- 恢复的仍是 **release-e2（481d3a7），不是候选**。

**审批 SHA（新旧两个，均写明）**

| 文件 | 旧（第一次构建，保留于 `restore13_authority_v1/`） | 新（当前 `restore13/`） |
|---|---|---|
| DEPLOYMENT_APPROVAL.json | `87cd531d338412bc33c0672c0e74de1c9f0f267d8dfa90d84f373bbd143c6869` | `16fdde876bcd8ea11e76b6cafa66a7d9c85edf4690e6ff688389aae0da3420b1` |
| ROOT_FINAL_REVIEW.json | `dd1b757f6844f44ec14b419e2a5770090d430b4b7fae42a19d3322b85f1d0e0f` | `207321e6f0ade446b93c575759574ff3395f6ae1239fc2c82a76f65b6076f4bd` |

- ROOT_FINAL_REVIEW 的 `approval_sha256` 指向新审批 SHA（已核对一致）；`independent_review_sha256` = `64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186`（B 指令）；`verdict` PASS。
- SOURCE_MANIFEST.json SHA256 `40a11d254fc4e8f98b3ecf408db5b18b8881d8b8e0fde68bf0f2905d649f47b8`，**未变**（清单只记录 .py 文件，审批 SHA 不参与其中）；`package` = `ophak_task_b_20261011/restore13`。
- 门链与 pytest 没有按字符串比对 `user_authority`（已 grep 确认：该字段只出现在 JSON 中，没有任何 .py 读取它）。改后：`pytest test_cpu_orchestration.py` → 7 passed；门链 → `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-13 2026-10-12T09:00:00+08:00`。
- restore12 → restore13 的差异见 `diff_restore13.txt`（SHA256 `988df6e54816a3027667d46eb97f8270f3359ad944cead39c45916cbdb174bae`，135 行）：身份字段、审批哈希与 user_authority。

**user_authority（主会话裁定，英文原文）**

> User-confirmed OPHAK_TASK_B_CUT_POLICY_20261011.md (sha256 64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186) GPU window: stop 481, run R0/C_A1/C_B1/C_B2/C_A2 (candidate m1/cut-min-tokens 9db0ee77, never deployed to production), restore 481 to release-e2 481d3a7; user instruction 2026-10-12 00:50 'task B continue'; main-session written release (COORDINATION_LOG '任务 B 放行') required before the window; no push; Ollama stays stopped.

**来源说明**：其中 "user instruction 2026-10-12 00:50 'task B continue'" 一句，是主会话（freetoken-06）转述的用户指示。主会话答复称，用户原话在其会话中说出："两件事，1、任务B继续执行，2、KT测试，你来主导……我要睡觉了，晚安，交给了。"op-hak 未直接见到该用户指示，不核实；授权表述由主会话负责。

**observation_until = 2026-10-12T09:00:00+08:00 的含义（已对照代码）**

- 它是 restore13 恢复后**只读夜间观察器**（`observe_overnight.py`）的截止时间。`post_night_observer.py` 把它作为 `--until` 传入。
- 观察器启动时若该时间已过，直接拒绝（`observation deadline must remain in the future`）；到点写 `terminal.json` 结束。观察器只采样，不停服、不回滚。
- 门链（`approved_attempt.load` → `deploy_conditional.require_root_final_review`）只打印该值，**不按时间判断**。因此它**不是 B 窗口的有效期上限**。
- 排期要求：W5 恢复与观察器启动必须在 09:00 之前完成，否则观察器不会启动。B 窗口估计 45–50 分钟。

## 5. 演练（`REHEARSAL_B.json`，all_pass = true，8/8）

定稿运行器 SHA256 `ce0da915b6b5…`，核对脚本 `877a9728…`。桩服务按预登记复现，演练只核对工装路径与判定函数的算术，**不是证据**。缩放 0.05 的控制组，G2 数值与漂移只是缩放伪影，不核对数值。

| 组 | 配置 | 终态 | 服务 | 结果 |
|---|---|---|---|---|
| R_positive | 缩放 1.0，五个服务各 21 条 | complete | 5/5 complete | T16-lite 成立；G1 成立（80/80）；G2 changed 成立（n = 14，中位数 2.7808 s，最小 2.7753 s）；G2 unchanged 成立（中位数 −0.0008 s）；G3 成立（40 对）；G5 成立；漂移 0；输入哈希与 INPUTS.json 一致；冷轮 T2/00 Δ = 2.7803 s（只报告） |
| R_a_output_tweak | C_A1 在 T2/03 改一个字符 | complete | 5/5 | T16-lite 不成立，只指出 T2/03；G3 指出 C_A1/C_A2 的 T2/03（首个不同字符位置 0） |
| R_b_param_missing | C_B1 解析值为 0 | param_gate_refused | R0、C_A1、C_B1 | `param_gate.json`：期望 32768，实际 0，ok = false；C_B1 没有请求；C_B2、C_A2 未启动 |
| R_c_wrong_pythonpath | C_B2 的 PYTHONPATH 指向 release | build_gate_refused | R0、C_A1、C_B1、C_B2 | `build_gate.json`：ok = false，导入的是 release 路径；无 serve.log；C_A2 未启动 |
| R_d_one_oom | C_B1 在 T2/05 OOM | complete | 5/5 | 死亡 1 次（C_B1，oom，done 14）；C_B2、C_A2 complete；G5 判"阈值策略未避开 E1，该参数不进生产" |
| R_e_two_oom | C_A1、C_B1 都在 T2/05 OOM | second_death_stop | R0、C_A1、C_B1 | 两次死亡；C_B2、C_A2 未启动 |
| R_f_startup_oom_one | C_A1 启动期 serve.log 为 OOM 文本 | complete | 5/5 | 死亡 1 次（C_A1，oom，无请求）；其余四个 complete |
| R_g_startup_two_plain | C_A1、C_B1 启动期退出（无 OOM 文本） | second_death_stop | R0、C_A1、C_B1 | 两次 launch_failed；C_B2、C_A2 未启动 |

演练记录的演变（都保留在服务器上，只有第三轮是定稿）：

- `rehearsal_pass1`：旧运行器（参数门无落盘记录）。流程全部按预期；不作为最终证据。
- `rehearsal_pass2`：旧运行器（启动失败不计死亡）。R_b、R_c、R_d、R_e 的终态按预期；不作为最终证据。
- `rehearsal`（第三轮）：定稿，8/8 通过，即本节所列结果。
- `REHEARSAL_B_report_attempt1_exit_path_bug.json`：核对脚本第一次生成的报告。它的退出码路径写错，导致所有组误判；仅此一项失败，已修正并保留。

## 6. 需要主会话判定或知悉的事项

1. **启动失败的清场**依赖 `oh_window` 的 `cleanup` 对已退出进程的处理（CPU 上未验证）。若返回失败，窗口按 `cleanup_blocked` 停止，需要主会话处理。
2. **真实启动器（RealLauncher）未在 CPU 上执行**（需要 GPU）。已核对：argv 与 `oh_window.compute_expected_argv` 一致（额外参数追加在末尾，与工装的 `build_argv` 产物相同）。构建门、参数门、死亡逻辑在桩服务与假对象上测试。
3. **GPU 锁的 owner 名**保留 A2 已验证的前缀 `OPHAK-TASKA-…`，仅用于记录，不影响判定。
4. **B_STOPPED**（`…/RESTORE481-MORNING-20261011-12/stopped.json`）：已核对，restore12 的停服脚本写回执的位置是 `run/stopped.json`，-10、-11 的回执都在该位置。
5. **W0 所需的协调日志行**：`任务 S 复核`（已有）、`任务 S 窗口结束`（已有）、`op-hak：任务 B P1 就绪`（本记录登记）、`任务 B 放行`（**尚未出现**；协调日志中只有指令封存说明的一处提及，不是放行行）。
6. **候选仍未部署到生产，未 push。** 481 当前运行 restore12，GPU 锁属于 `production:release:RESTORE481-MORNING-20261011-12`。

## 7. 证据索引（SHA256，服务器 `/data2/FreeToken/development/ophak_task_b_20261011/` 与运行目录）

| 文件 | SHA256 |
|---|---|
| `task_b_runner.py` | `ce0da915b6b54154baf545bee6cb9ba33af5f717eca4590b556d7c0acf622a51` |
| `stub_b_server.py` | `1fc404e91e471257e7f54ffe853968ec560b061fa5e665307ac0b501458974b4` |
| `analyze_task_b.py` | `83a4f0f9224d56611f93897e6bf2609a9cf2ab2b026734269568cb9e50144f62` |
| `test_task_b_runner.py` | `ef16c7b8aa051a24917e880af1ed524e1751beb0c56f7990f713b8690e7ae8bb` |
| `make_rehearsal_b_report.py` | `877a97283144c44933c3c0eaf4d764bbf4e2877bf3a0b48cae3e7308a7a8d843` |
| `run_rehearsals_b.sh` | `a5235068cde59794b103190390af52f816fe336c4f4a21d12f3e7d3057b6bc59` |
| `build_restore13.py` | `ee103bf215e841de97a4549b682045ed3310c086d32e76206f73f397b9ba6f49` |
| `INPUTS.json` | `7931e9a9854526d898e153feb723a785d433ab2fdd6192d8b96b6ada31b6a934` |
| `REHEARSAL_B.json` | `40d33b693b8a187f74e0fee76664fd365ce7b0b4ea94609f6f5de33608a9dbf4` |
| `offline_release.json` | `f16c855f445932c703131d6af20ea62ebbf0846f9b577953e2ff92df7cfc1892` |
| `offline_candidate.json` | `b7fb0dc75d49c7ae7ee68293a32ca723418c40ad35fbb128eaedd308134bb7ba` |
| `restore13/DEPLOYMENT_APPROVAL.json` | `16fdde876bcd8ea11e76b6cafa66a7d9c85edf4690e6ff688389aae0da3420b1` |
| `restore13/ROOT_FINAL_REVIEW.json` | `207321e6f0ade446b93c575759574ff3395f6ae1239fc2c82a76f65b6076f4bd` |
| `restore13/SOURCE_MANIFEST.json` | `40a11d254fc4e8f98b3ecf408db5b18b8881d8b8e0fde68bf0f2905d649f47b8` |
| `diff_restore13.txt` | `988df6e54816a3027667d46eb97f8270f3359ad944cead39c45916cbdb174bae` |
| `restore13_authority_v1/DEPLOYMENT_APPROVAL.json`（旧） | `87cd531d338412bc33c0672c0e74de1c9f0f267d8dfa90d84f373bbd143c6869` |
| 指令 `OPHAK_TASK_B_CUT_POLICY_20261011.md` | `64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186` |
| 预登记 `PREREG_TASK_B_v2.json` | `8df5ee4901795d287bed22cfaadbaef3515c89f530c4f9df26a5798489f9152d` |
| 候选提交 | `9db0ee776c25afa8d2719ab700b2de7ccc606142` |
