# KIMI 执行手册：阶段二第 1 轮（2026-10-11）

> 编写：主会话（Claude）。执行：KIMI。裁定：用户。
> 本手册是唯一的执行依据。手册中没有写到的操作一律不做；遇到手册没有覆盖的情况，**停下来写报告，不要自行判断**。

---

## 0. 先读这一节

### 0.1 你要完成什么

| 阶段 | 内容 | 是否用 GPU | 何时 |
|---|---|---|---|
| **阶段 1** | 现状核对、版本登记表、两套 T16 工装适配、hybrid 验证工装准备、WSL2 客户端说明，全部在 CPU 上完成并演练 | **不用** | 现在开始 |
| 审核门 | 主会话审核阶段 1 的交付物 | — | 阶段 1 完成后 |
| **阶段 2** | 停 481 → T16（D05）→ T16（D09 修复）→ hybrid 验证 → 恢复 481 | 用 | 审核通过后，且不早于 09:00 |

**阶段 1 完成后必须停下等审核。** 未经主会话书面通过（会写在本文件末尾的"审核记录"一节），不得开始阶段 2。

### 0.2 红线（任何情况下都不能做）

1. 不推送任何 git 分支（`git push` 禁止）。
2. 不启动 Ollama：`docker start ollama` 禁止。另一个容器 `ollama_pre_opt_20260727_193031` 也不要碰。
3. 不修改论文（`paper/` 目录）。
4. 不修改、移动、删除任何已有的证据目录和原始文件，包括 `runs/`、`/data2/_shared/runs/ft_rounds/` 下的旧轮次，以及 `development/` 下其他人建的目录。你的所有产出都写在**新建的目录**里。
5. 不手动删除 `/data2/_shared/gpu.lock`。不用 `kill` 结束别人启动的进程。停止 481 只能用第 3.1 节写明的脚本。
6. 阶段 1 不能占用 GPU：不起模型服务，不取 GPU 锁，所有 CPU 测试都要设置 `CUDA_VISIBLE_DEVICES=`。
7. 任何 GPU 步骤失败时，**不重试**，直接进入"失败处理"（第 3.7 节）。
8. 测速（AIPerf）期间，测试服务器上不能同时跑其他 CPU 密集任务。

### 0.3 记录规范

- 工作目录：本地 `D:\00.开发\2026\03-模型实验\freetoken\freetoken\development\kimi_phase2_20261011\`；服务器 `/data2/FreeToken/development/kimi_phase2_20261011/`。两边内容保持一致。
- 每完成一步，向本地 `plan/COORDINATION_LOG.md` **末尾追加一行**，格式：
  `- <真实当前时间 ISO8601，+08:00> KIMI：<步骤编号> <结果一句话> <产出文件路径>`
  时间必须用命令实际取得（`date "+%Y-%m-%dT%H:%M:%S+08:00"`），不能估计。
- 每个产出文件写完后，计算 SHA256 并记入该步的报告。

### 0.4 环境速查（主会话于 2026-10-11 02:30 核实）

| 项 | 值 |
|---|---|
| 测试服务器 | `ssh 9`（172.16.108.9）。双路 48 核，GPU 为 RTX 4090（NUMA 节点 1，奇数 CPU） |
| FreeToken 主 venv | `/data2/FreeToken/venv`（`freetoken` 以可编辑方式安装，默认指向 `/data2/FreeToken/src/FreeToken/python`） |
| 测试工具 venv | `/data2/FreeToken/evaluation/toolchain/venv-aiperf`（aiperf 0.11.0）、`venv-eval`（openai、pytest）；版本以 `freeze-20261008T173559Z.txt` 为准 |
| 模型 | `/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay`，服务名 `Qwen3.8-Flash-Next-NVFP4` |
| GPU 锁 | `/data2/_shared/gpu.lock`。生产服务运行时由其监管进程持有 |
| 生产服务状态文件 | `/data2/FreeToken/run/production.active.json` |
| 当前生产服务 | 481d3a7，审批号 `RESTORE481-MORNING-20261011-07`，运行目录 `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07`，地址 `http://172.16.108.9:8095/v1` |
| 生产启动参数 | 见 `production.active.json` 的 `argv`：`taskset -c 1,3-47 ft serve … --host 172.16.108.9 --port 8095 … --moe-strategy offload … --prefill-layer-major …` |
| 当前在跑的进程 | `release_control.py`（监管进程）、`monitor_health.py`、`ft serve`、`post_night_observer.py`、`observe_overnight.py`（运行到 09:00）。**都不要动** |
| 生产控制接口 | `/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2/release_control.py`，支持 `--plan` / `--start` / `--stop`；平时通过 `development/morning_restore07_20261011/` 下的审批脚本调用 |

### 0.5 版本与"版本切换"

**原理。** 同一个 venv 可以加载不同版本的代码。服务启动时设置 `PYTHONPATH=<工作树>/python`，覆盖可编辑安装的默认路径，同时清除其他 `FT_*` 环境变量。目标工作树必须是干净的（`git status --porcelain` 为空）、提交号与预期一致，并且原生扩展（`.so`）能通过二进制清单核对。具体由各工装中的 `validate_worktree` / `require_native_extension_layout` 检查，**不要手动设置环境变量起服务**。

本轮涉及的版本：

| 名称 | 工作树 | 提交号 | 角色 |
|---|---|---|---|
| 发布版 481 | `/data2/FreeToken/wt/release-e2` | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` | 基线和 T16 的父版本 |
| D05 修复 | `/data2/FreeToken/wt/d05-decode-align-481-20261011` | `730b58c9`（取完整哈希填入） | T16 候选 1 |
| D09 修复 | `/data2/FreeToken/wt/d09_fix_20261011` | `7d8d389e`（取完整哈希；包含 bd57） | T16 候选 2 |
| D09 页守恒 | `/data2/FreeToken/wt/d09-page-conservation-20261010` | `bd57cfdccc2a935d46cb0a89b8b36be7a18706de` | 仅作参考，batch163 用的就是它 |

**hybrid 不是代码版本，而是启动参数。** 在 481 的生产启动参数上只改两处：
1. `--moe-strategy offload` 改为 `--moe-strategy hybrid`；
2. 前缀 `taskset -c 1,3-47` 改为 `numactl --interleave=all taskset -c 1,3-23,25,27-47`。

其余参数逐项不变。

---

## 1. 阶段 1：CPU 准备（不用 GPU、不停 481）

每一步都按"目的 / 操作 / 成功判据 / 产出 / 失败处理"执行。

### 1.1 交接现状核对

- **目的：** 确认接手时的状态，避免与其他执行者冲突。
- **操作（只读）：**
  ```bash
  ssh 9 'date; uptime; nvidia-smi; cat /data2/FreeToken/run/production.active.json; ls -la /data2/_shared/gpu.lock; docker ps -a --format "{{.Names}} {{.Status}}"; ps -eo pid,etime,args | grep -E "python|ft serve|aiperf" | grep -v grep'
  ```
- **成功判据：**
  - 生产服务是 481d3a7，审批号以 `-07` 结尾；
  - 容器 `ollama` 处于 Exited 状态；
  - 除 0.4 节列出的 5 类进程外，没有其他 `development/` 下的 Python 任务在运行。
- **产出：** `kimi_phase2_20261011/00_HANDOVER_STATE.md`，粘贴原始输出并逐项写明是否符合。
- **失败处理：** 任何一项不符合，就停下，在报告中写明差异，等主会话处理。

### 1.2 版本登记表

- **目的：** 服务器上有约 70 个工作树。弄清每个版本是什么，未登记的版本不得进入后续的组合测试。
- **操作：** 遍历 `/data2/FreeToken/wt/` 下的每个目录（`.bundle` 文件另列一张表，只记文件名和 SHA256），对每个工作树记录：
  ```bash
  git -C <wt> rev-parse HEAD
  git -C <wt> log -1 --format='%ci %s'
  git -C <wt> status --porcelain | wc -l
  git -C <wt> merge-base --is-ancestor 481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9 HEAD && echo yes || echo no
  git -C <wt> merge-base --is-ancestor bd57cfdccc2a935d46cb0a89b8b36be7a18706de HEAD && echo yes || echo no
  ```
  再到本地 `plan/02_开发任务/` 的卡片、`plan/COORDINATION_LOG.md` 和 `plan/01_测试与调研/results/` 中，按提交号查找这个版本的 T16/T17 结果和实测效果。**查不到就写"待核"，不要推测。**
- **成功判据：**
  - 每个目录都有一行记录；
  - 第 0.5 节表中 4 个版本的记录与该表一致。
- **产出：** `development/VERSION_REGISTRY_20261011.md` 与 `.json`。字段：工作树、HEAD、提交时间与标题、是否干净、是否包含 481、是否包含 bd57、关联卡片、T16/T17 状态（附批次号）、实测效果或负结果、备注。
- **失败处理：** 某个目录读取失败，就在该行写明错误并继续处理下一个；不要修复或清理任何工作树。

### 1.3 两套 T16 工装适配（D05 修复、D09 修复）

- **背景：** 现有的 T16 工装 `/data2/FreeToken/development/d09_gpu_reapplication_20261010/protocol_t16/`（`owned_launch.py`、`runner.py` 等）是为 bd57 写的，候选提交号、工作树、前置轮次、原生扩展绑定都写死在代码里。batch163 用它跑出了 8 个服务、100 次调用、kept 的结果，是经过验证的工装。
- **操作：**
  1. 把整个 `protocol_t16/` 目录**复制**两份，分别放到 `kimi_phase2_20261011/t16_d05/` 和 `kimi_phase2_20261011/t16_d09fix/`。**原目录不能改。**
  2. 在副本中只允许修改以下内容：
     - 轮次标识：`E2-D05-T16-20261011` / `E2-D09FIX-T16-20261011`；
     - 候选提交号（完整哈希）和候选工作树路径（见 0.5 节）；
     - 前置轮次检查（`required_rounds`）：改为要求 batch163（`E2-D09-T16-reapply-bd57-20261010`）已封存为 kept；如果原代码的检查方式不支持这样改，写明原因并停下；
     - 原生扩展绑定：仿照 bd57 的做法（参考 `d09_native_provenance_bd57.json`），让候选工作树使用与 release-e2 相同、已批准的原生扩展，再用原有的 `require_native_extension_layout` 检查。
  3. **不能改的内容：** 父版本 481d3a7 和父工作树 release-e2、测试协议（服务数、调用数、各臂设置、冻结输入）、判定逻辑（sequence 与 h2d 全部 SAME）、GPU 锁和清理逻辑。
  4. 生成副本与原目录的 `diff -ru`，确认只改了上面允许的位置。
  5. 运行副本中原有的 CPU 测试（如 `test_native_candidate_binding.py`），设置 `CUDA_VISIBLE_DEVICES=`。
  6. 运行 `owned_launch.py` 自带的文件演练（file dry-run）：先用 `--help` 查清参数。现在生产服务持有 GPU 锁，如果演练因此拒绝运行，就使用代码里已有的注入模式（`inject_lock_and_idle`）。**不能取得真实的 GPU 锁，也不能启动服务。**
- **成功判据：** 两套工装的 diff 都只涉及允许的位置；CPU 测试全部通过；文件演练生成回执且没有报错。
- **产出：** 两个目录下各一份 `CPU_READINESS.md`，内容包括：diff 全文、测试输出、演练回执路径和 SHA，以及一条"阶段 2 实际要执行的命令"（写全，先不执行）。
- **失败处理：**
  - 某一套失败，就停止那一套，另一套可以继续做；
  - 不要为了让测试通过而改判定逻辑或协议；
  - 原因写进 `CPU_READINESS.md`。

### 1.4 hybrid 验证工装准备

- **背景：** 重试 2 的工装 `/data2/FreeToken/development/d08_d10_gpu_retry2_20261011/`（`gpu_window.py`、`hybrid_service.py`、`window_measure.py`、`warmup_client.py`）昨晚在真实 GPU 窗口里跑通了：起 hybrid 服务、预热、AIPerf 测速、恢复 481 都成功过。
- **操作：**
  1. 把该目录复制到 `kimi_phase2_20261011/hybrid_verify/`，原目录不能改。在副本中**删除 η 与 D0 两段测量**，本轮不需要；只保留服务起停、预热、AIPerf 测速和恢复相关的逻辑。
  2. **冻结负载**，每个文件都记录 SHA256：
     - **X**：`/data2/FreeToken/development/d10_reanalysis_20261010/closed_loop_20261010/inputs_X.jsonl`，SHA 必须为 `f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162`，两条不同内容的提示，约 1.2K token。
     - **LC1（长上下文单路）**：`/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/round-01.payload.json`，真实 agent 对话，约 87,100 token。
     - **LC2（长上下文两路，内容不同）**：
       - 第一条用 `/data2/_shared/runs/ft_rounds/E2-R046g/G_seed12k/round-01.payload.json`；
       - 第二条从 LC1 截取：按顺序逐条加入 messages，用 481 的 `freetoken.tokenizer.tokenize.TokenizeManager` 计算渲染后的 token 数，在不超过 32,000 token 的前提下保留尽可能多的**完整**消息；保留下来的最后一条消息的角色必须是 user 或 tool，如果是 assistant，就去掉它。
       - 记录两条的实际 token 数和 SHA。
     - **不要使用** `probe_cold32k.py` 生成的 32K 文本，也不要用 R048b 的 `dec32k_s3A/B`：它们是同一段文字重复几百遍拼成的，s3A 和 s3B 只有开头一行不同。
  3. 把测量编排改成第 2.4 节的顺序和清单。服务起停、预热、AIPerf 调用都复用原来的函数。
  4. 加入 quality60：命令格式见 `/data2/FreeToken/evaluation/quality60/README.md`，即 `venv-eval/bin/python phase3_sdk.py --api-base http://127.0.0.1:<测试端口>/v1 --model Qwen3.8-Flash-Next-NVFP4 --prompts /data2/_shared/test_prompts_60.json --run-dir <新目录>`。
  5. **参数合法性检查：** 每个服务的最终启动参数，都要先用 481（release-e2）自己的参数解析器做 dry-run，有未知参数就拒绝。这一步要写成 CPU 测试。
  6. 运行副本原有的 CPU 测试，以及新增的测试：负载 SHA 校验、LC2 截断规则、启动参数 dry-run、quality60 的 CPU 测试（README 中的 pytest 命令）。
- **成功判据：** 所有 CPU 测试通过；三份负载冻结完成；hybrid 的启动参数与生产启动参数逐项对比，只有 0.5 节写明的两处差异。
- **产出：** `hybrid_verify/CPU_READINESS.md`，包含负载清单与 SHA、启动参数对比、测试输出、预计时间表，以及"阶段 2 实际要执行的命令"。
- **失败处理：** 停下来写明原因，不要用 eager 循环或自写客户端代替 AIPerf 和 quality60。

### 1.4b 停止与恢复 481 的准备

- **目的：** 阶段 2 的第一步是停止 481，最后一步是恢复 481。这两步都在 CPU 上提前演练好，与其他准备一起送审，不在 GPU 窗口里临时准备。
- **操作：**
  1. 阅读 `development/morning_restore07_20261011/README.md` 和 `stop_approved_restore.py`，写出停止当前生产服务（审批号 `RESTORE481-MORNING-20261011-07`）的**确切命令**和预期输出。现在不执行。
  2. 把 `morning_restore07_20261011/` 复制为 `kimi_phase2_20261011/restore08/`，原目录不能改。只替换身份信息：审批号 `-07` 改为 `-08`、运行目录、批准时间等。保留 df77cb 基准对比和回滚逻辑。用 `diff -ru` 确认只改了身份信息。
  3. 设置 `CUDA_VISIBLE_DEVICES=`，运行副本中的 `test_cpu_orchestration.py`。
- **成功判据：** 停止命令已写清楚；restore08 的 diff 只涉及身份信息；CPU 测试通过。
- **产出：** `restore08/CPU_READINESS.md`，内容包括：停止命令、启动命令、SDK 冒烟命令、回滚命令、diff、测试输出。
- **失败处理：** 停下来写明原因。**这一步不通过，阶段 2 就不能开始**，因为停了 481 之后无法保证能恢复。

### 1.5 WSL2 客户端说明（给用户用）

- **产出：** `freetoken/evaluation/toolchain/WSL2_CLIENT_SETUP.md`，内容包括：
  1. 在办公电脑的 WSL2 中，按 freeze 文件复建 `venv-aiperf` 和 `venv-eval`（给出命令）；
  2. 生产服务监听 `172.16.108.9:8095`，可以直接访问；测试服务只监听 127.0.0.1，需要通过 `ssh -L` 隧道访问（给出命令）；
  3. 三类测试的边界：
     - S（本机性能）：只在服务器上测；
     - F（功能与质量）：可以在 WSL2 中做；
     - N（局域网体验）：可以在 WSL2 中做，但要单独建立基线，不能和 S 的数据混用；
  4. 禁止事项：不要在服务器做本机测速时，从 WSL2 并发发送请求。
- **成功判据：** 文档中的命令都能在服务器或本地实际运行（工具版本检查和隧道连通性检查即可，不发生成请求）。

### 1.6 阶段 1 交付并停止

- 写 `kimi_phase2_20261011/STAGE1_SUMMARY.md`：列出每一步的状态（完成 / 失败 / 跳过）、产出文件及 SHA、遇到的问题，以及阶段 2 的完整命令清单。
- 在协调日志中追加一行"阶段 1 完成，等待主会话审核"。
- **然后停止，等待审核。**

---

## 2. 阶段 2 的测量设计（预先登记，阶段 1 中按此准备，审核通过后执行）

### 2.1 时间与压力测试告知

- 最早 09:00 开始，即 481 的观察窗口结束之后。总时长约 4.5 小时，期间 481 生产服务不可用。
- 属于压力测试：T16 两次共约 2 小时；hybrid 运行期间约 21 个 CPU 核满载，累计约 40 分钟。主会话已提前告知用户。

### 2.2 T16（D05 修复）

- 用 `t16_d05` 工装，按 `CPU_READINESS.md` 中的命令执行。
- **判据：** 与 481d3a7 相比，开关关闭时所有臂的 sequence 和 h2d 都是 SAME。
- **判据不通过**（某臂不是 SAME）：记为 not_met，不重试，**继续执行 2.3**，因为两项修复互不依赖。
- **工装失败**（failed_harness）：不重试，**跳过 2.3**，因为两套工装同源，大概率会遇到同样的问题。直接执行 2.4（hybrid 验证使用另一套工装），最后执行 2.5。

### 2.3 T16（D09 修复）

同 2.2，使用 `t16_d09fix` 工装。

### 2.4 hybrid 验证（≤120 分钟）

**服务顺序：** O1（offload）→ H1（hybrid）→ H2（hybrid，全新冷启动）→ O2（offload）。每个服务都只监听 127.0.0.1 的测试端口。除 H2 外，每个服务先发 2 个不计成绩的预热请求，内容与恢复 481 时的 SDK 冒烟请求相同。

**通用设置：** temperature=0，max_tokens=256，ignore_eos=false，速度一律用 AIPerf ITL 计算（1000 / ITL ms）。

| 服务 | 测量内容（按顺序） |
|---|---|
| O1 | X 单路 ×2；X 两路 ×2；LC1 单路 ×2；LC2 两路 ×2；quality60 ×1 |
| H1 | 与 O1 完全相同 |
| H2 | 全新启动，**不预热**，只发 X 单路 ×1 |
| O2 | X 单路 ×2；X 两路 ×2；LC1 单路 ×2；LC2 两路 ×2（不跑 quality60） |

**预登记判据：**

| 编号 | 问题 | 判据 | 判定 |
|---|---|---|---|
| J1 | 两路收益（主判据） | H1 的 X 两路每路速度 ≥ (O1 与 O2 的 X 两路均值) × 1.15 | 成立 / 不成立 |
| J2 | 测量漂移 | O1 与 O2 的 X 两路均值相差不超过 5% | 超过就标"漂移"，J1 不下结论 |
| J3 | 质量等价 | H1 的 quality60 得分 ≥ O1 得分 − 3 | 不成立时，hybrid 不进入后续组合测试 |
| J4 | 自身复现性 | 三组比较：H1 两次 X 单路之间；H1 两次 X 两路之间（按同一条提示配对）；H2 的 X 单路与 H1 第一次 X 单路之间。比较方法：拼接 reasoning_content 与 content，找第一个不同的字符位置，与 `development/d08_hybrid_review_20261011/output_compare.py` 相同 | 全部逐字相同记为"可复现"；任一组不同，记为"受缓存或时序影响"，交用户裁定 |
| J5 | 长上下文（只记录，不作判据） | LC1 单路、LC2 两路，H1 与 O 均值的比值 | 只报告比值 |
| — | 输出过短 | 某次请求生成不足 128 token 时，该次速度不计入，并在报告中标注 | — |
| — | 异常下限 | 任一项每路速度低于 7.8 | 判为异常，不下结论 |

### 2.5 恢复 481

- 使用阶段 1 第 1.4b 步准备并经过审核的 `kimi_phase2_20261011/restore08/`。
- 启动后执行 SDK 冒烟，并与 df77cb 基准逐项对比 15 个稳定字段和完整启动参数。
- **全部一致** 才算恢复成功。

### 2.6 停 481 的方法（阶段 2 第一步）

- 先确认 09:00 后两个观察进程已经自行退出（`ps` 查看）。如果还在运行，停下来报告，不要 kill。
- 执行阶段 1 第 1.4b 步中已经审核过的停止命令，不要临时改写。
- 停止后核对三项：`gpu.lock` 已经释放（由监管进程释放）；`nvidia-smi` 中没有计算进程；`production.active.json` 已经清除或标记为已停止。

### 2.7 失败处理（阶段 2 通用）

| 情况 | 处理 |
|---|---|
| 工装报错（服务没起来、脚本异常、超时） | 当前步骤记为 failed_harness，**不重试**。执行该工装自带的清理，然后跳到 2.5 恢复 481 |
| 判据不通过（比如 T16 不是 SAME） | 记为 not_met，不重试，按 2.2 的规则继续 |
| 清理失败（端口占用、GPU 未释放） | 等待最多 120 秒并轮询。仍然失败就停下，写 `CLEANUP_BLOCKED.md`，不要强行处理 |
| 481 恢复失败 | 按 restore07 目录中的回滚脚本（`start_approved_rollback.py` / `wait_rollback_and_smoke.py`）回滚。回滚也失败，就写 `PRODUCTION_DOWN.md`，并在协调日志中标注"紧急"，等待处理 |
| 发现手册没有覆盖的情况 | 停下来写报告 |

### 2.8 阶段 2 的产出

- `kimi_phase2_20261011/STAGE2_RESULT.md`：
  - 每一步的终态；
  - T16 两次的判定和批次号；
  - J1–J5 的结果表，附原始数值和计算过程；
  - 恢复结果；
  - 所有证据路径与 SHA。
- 原始 AIPerf 导出文件、quality60 运行目录、服务日志，都保存在各自的新目录中。

---

## 审核记录（由主会话填写）

- 阶段 1 审核（2026-10-11T08:53:17+08:00，主会话）：**有条件通过**。见 `plan/KIMI_STAGE1_REVIEW_20261011.md`（SHA256 66744c87861ee98c72a801a00a615561303fab0268ca6b31e0280cef8d9197db）。
  - 先完成 S0 的三项修改：D05 默认关闭检查改为"参数零差异 + 清除环境变量"；hybrid 窗口上限改为 9000 秒；restore08 观察截止时间改为 19:00。
  - LC2 本窗口取消：手册指定的 `G_seed12k` 是合成文本，属主会话错误。
  - 第 1.4 节"只有两处差异"的判据有误，以 127.0.0.1:8123 为准。
- 阶段 2 放行：**放行**，条件是 S0 完成且不早于 09:00，按审核文件第三节的新顺序执行（停 481 → dry-run ×2 → hybrid → 主会话独审 → T16 D09fix → T16 D05 → 恢复）。T16 的独审文件和用户批准文件由主会话在 S2 之后写入。
- 阶段 2 结果复核（2026-10-11T10:10:59+08:00，主会话）：上午窗口中 S3 hybrid 为 failed_harness，根因是主控把窗口截止原值交给服务；S4 被跳过是主会话失败路由的问题，不是 KIMI 执行的问题。晚间窗口按 `plan/KIMI_EVENING_WINDOW_20261011.md`（SHA256 dd89778a31525ebfed975a459c9bc5031c495837136c7074d2dfe03599e7decb）执行：
  - E0（纯 CPU）：修复 hybrid、重建准入、真实入口演练、构建 restore09。
  - 19:00 后：停 481 → T16 D09fix → T16 D05 → hybrid → 恢复 481。
  - 4 份 T16 治理文件已在 10:05 封存。
