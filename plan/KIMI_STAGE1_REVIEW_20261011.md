# 阶段 1 审核结论与阶段 2 放行条件（主会话 → KIMI，2026-10-11）

> 审核对象：`development/kimi_phase2_20261011/STAGE1_SUMMARY.md`（SHA256 2428eaf8…75a484）及其列出的全部产出。
> 本文件是 `plan/KIMI_RUNBOOK_PHASE2_20261011.md` 的补充。两者冲突时**以本文件为准**。本文件写定后不再修改，后续审核另开新文件。
> 审核人：主会话（Claude），非阶段 1 产出的作者。

---

## 一、总体结论

**阶段 1 有条件通过。** 先完成第三节 S0 的三项修改，再按第三节的新顺序执行阶段 2。

KIMI 做对的事：D05 阻断项和 LC2 不可行都是先停下来报告，没有擅自修改判定逻辑；restore08 的 diff 只改了身份信息；版本登记表凡查不到的都写了"待核"，没有推测。

| 步骤 | 结论 | 说明 |
|---|---|---|
| 1.1 交接核对 | 通过 | — |
| 1.2 版本登记表 | 通过 | D05 树的系谱已由主会话核实（见 2.6）。`d09-page-conservation-20261010`（bd57）现在不干净（3 处改动），本窗口不使用这个树，留待以后查明 |
| 1.3 T16 D09fix | 通过 | diff 只涉及允许位置。7d8d389e 相对 bd57 只改了 `scheduler/cache.py` 和测试，没有新增开关，原判定逻辑直接适用 |
| 1.3 T16 D05 | **需修改** | 见 2.1，按 S0-1 修改 |
| 1.4 hybrid 工装 | **需修改** | 见 2.2、2.3、2.5，按 S0-2 修改 |
| 1.4b restore08 | **需修改** | 见 2.4，按 S0-3 修改 |
| 1.5 WSL2 说明 | 通过 | — |

---

## 二、对 6 个待裁定项的裁定

### 2.1 D05 的 T16 默认关闭检查：改为"参数零差异 + 环境变量清除"（主会话授权修改）

**事实（主会话已核实）**
- D05 候选（730b58c9）没有新增 CLI 参数。开关是环境变量 `FREETOKEN_D05_ALIGNED_DECODE_STATE`：`env.py` 中的 `D05_ALIGNED_DECODE_STATE = EnvBool(False)`，前缀 `FREETOKEN_`。
- 基础工装的 `environment()` 会复制整个 `os.environ`，只清除 `FT_DEV_*` 和 `FT_D3_*`，**不会清除这个变量**。因此原工装既检查错了对象，也没有保证开关处于关闭状态。
- 关闭时的代码路径：`scheduler.py` 中只有 `if ENV.D05_ALIGNED_DECODE_STATE:` 一个分支；`Req` 新增的字段在关闭时不会被读取。

**裁定。** 默认关闭检查只是判定的前置条件，SAME 判定本身（sequence、h2d）不变。新检查比原来**更严格**：候选不允许有任何参数增量，并且两臂的环境中都不能出现 D05 开关。

**只改 `t16_d05/runner.py`，具体如下：**
1. 常量：
   - `DEFAULT_OFF_CANDIDATE_ARGS = {}`；
   - 新增 `DEFAULT_OFF_ENV = 'FREETOKEN_D05_ALIGNED_DECODE_STATE'`；
   - 删除 `PUBLIC_DEFAULT_OFF_FLAG` 和 `PARSED_DEFAULT_OFF_ARG`，并删除所有对它们的引用。
2. `CandidateRunner.environment()`：在 `super().environment(...)` 之后，删除 env 中所有以 `FREETOKEN_D05_` 开头的键。父版本和候选两臂都调用这个函数，所以两臂都会被清除。其余行为不变。
3. `CandidateRunner.assert_default_off_args(parent, candidate)`：只保留一行，`base['strict_args'](parent, candidate, DEFAULT_OFF_CANDIDATE_ARGS)`。也就是说，除了 `_unique_suffix` 的 PID 之外，任何参数差异都拒绝。
4. 回执字段：`'default_off_public_flag': {...}` 改为 `'default_off_env': {DEFAULT_OFF_ENV: 'absent'}`。
5. `adapter_self_test()` 改为以下 5 条断言，通过时打印 `D05 ADAPTER SELFTEST PASS`：
   - (a) 只有 PID 不同的候选参数：接受；
   - (b) 候选多出 `message_boundary_ckpt='False'`：拒绝；
   - (c) 候选 `server_port` 不同：拒绝；
   - (d) 临时设置 `os.environ[DEFAULT_OFF_ENV]='1'` 后调用 `environment()`，返回的 env 中**没有**这个键（测完恢复 `os.environ`）；
   - (e) 身份绑定断言，保持原样。
6. **不能改：** `owned_launch.py`、基础工装 `t16_private_port_dryrun_r062_v1.py`（哈希钉住）、`check_det` 和 sequence/h2d 比较、锁与清理逻辑。

**验证（`CUDA_VISIBLE_DEVICES=`）：**
- `runner.py --self-test` 通过；
- `pytest test_native_candidate_binding.py -q` 通过；
- `--dry-run-injected --card D05` 重新跑一次：预期仍然只在 ps 扫描处被拒绝（因为 481 还在运行），在此之前的各项检查全部通过；
- 重新生成 `diff_d05.txt`；
- 在 `t16_d05/CPU_READINESS.md` 末尾追加"修订 v2"一节，写明上面各项的输出和新的源文件 SHA256。

**失败处理：** 任意一项不通过，就停止 D05 这一套，在协调日志中记录，阶段 2 照常执行（只是不跑 D05 的 T16）。不要为了让测试通过去改其他文件。

### 2.2 LC2：本窗口取消（主会话手册有误）

- **更正。** 手册给 LC2 第 1 路指定的 `G_seed12k/round-01` 实际上也是合成文本：173 行中有 168 行是同一段"模型验收记录"。这和手册自己禁止的 32K 合成文本是同一类。这是主会话的错误，KIMI 照手册执行，没有责任。
- 另外，LC1 第 1 条消息单独就有 87,100 token，所以"按完整消息截取"的规则不可行，KIMI 的判断正确。`G_seed_45k` 和 LC1 是同一份代码导出（开头相同），`G_two` 是短提示。服务器上目前**没有第二条内容不同的真实长负载**。
- **裁定。** 本窗口不跑 LC2。不采用 KIMI 的前缀提案，原因有两点：截断后会丢掉原来的提问；第 1 路仍然是合成文本。J5 只报告 LC1 单路的比值。"内容不同的真实长上下文两路"留到组合测试阶段，先建好真实负载集再测。
- 当前准入本来就不含 LC2（`lc2_status: excluded_pending_main_session_adjudication`），代码不用改。重建准入（见 2.5）时，如果这个字段可以通过参数设置，就改成 `dropped_by_main_session_20261011`；如果不能，保持原值，以本文件为准。

### 2.3 测试服务的地址和端口：采用 127.0.0.1:8123（主会话手册自相矛盾，更正第 1.4 节）

- 采用第 2.4 节的要求。测试服务不能占用生产使用的局域网地址：否则测量期间局域网客户端的请求会打进测试服务，既污染测量结果，又会把测试服务的回答返回给用户。
- 第 1.4 节的成功判据更正为：
  - O1/O2 与生产启动参数有 2 处差异（`--host`、`--port`）；
  - H1/H2 有 4 处差异（host、port，加上 0.5 节的 2 处）；
  - O 与 H 之间恰好是 0.5 节的 2 处。
- KIMI 现在的实现符合这个标准，不用改。

### 2.4 restore08 的观察截止时间：改为 2026-10-11T19:00:00+08:00

- **理由。** 设成 10-12 09:00，观察进程会一直运行到明天上午。用户今晚还要做代码调整，可能进行组合测试；按手册规则，观察进程在运行时不能停 481（也不能 kill 它），今晚的窗口就会被锁住。改成 19:00，预计恢复时间是 13:30 到 15:00，可以观察 4 到 5 小时。
- **操作：**
  1. 只修改 `DEPLOYMENT_APPROVAL.json` 的 `observation_until`；
  2. 重新计算 `approval_sha256`，重写 `ROOT_FINAL_REVIEW.json`：
     - `approval_sha256` 填新值；
     - `independent_review_sha256` 填**本文件**的 SHA256（以服务器上那份为准：用 scp 以二进制方式复制过去，两边分别计算，确认一致）；
     - `pending_independent_review` 改为 `false`；
     - 其余字段不变。
  3. 两侧分别运行 `pytest` 7 项，并重放门链（`GATE_CHAIN_PASS`）；
  4. 重新封存为 0444。
- **补充规则。** 如果 481 恢复的时间晚于 18:30，`observe_overnight.py` 会拒绝启动，因为截止时间必须在未来。这种情况**不算恢复失败**：481 已经在提供服务，只需在协调日志记录"观察进程未启动（截止时间已过）"，不要回滚。

### 2.5 hybrid 窗口上限：6900 秒改为 9000 秒

- 按 KIMI 的估计，总时长 80 到 130 分钟，上限 115 分钟偏紧，而触到上限会让整个窗口作废。取消 LC2 以后，主会话估计约 80 到 105 分钟。上限放宽到 150 分钟，只是为了留出余量，不代表计划要用满。
- 操作：把旧准入改名为 `ROOT_ADMISSION.v1_window6900.json` 保留下来，`window_limit_seconds=9000`，重跑 `prepare_root_admission.py` 重建准入并封存 0444，然后重跑工装 pytest 和准入回读校验（`PIN_AND_ARGV_GATE_PASS`）。在 `CPU_READINESS.md` 末尾追加"修订 v2"一节，写明新准入的 SHA。

### 2.6 D05 树的系谱（登记表中原为"待核"）：已核实

- `d05-decode-align-481-20261011` 的 HEAD 为 730b58c96527fe5bf117d1f3c2430e405173d28b，在 481d3a7 之上恰好 5 个提交（bb7cf6d4 → 72171f4a → 89d3816d → 181a510c → 730b58c9），工作树干净。相对 481 共改了 6 个文件（README、core.py、env.py、scheduler/cache.py、scheduler/scheduler.py、测试）。
- 登记表这一行由 KIMI 追加"主会话 10-11 核实"的说明，不改其他内容。

### 附：两处不需要修改、但要写进报告的说明

- **LC1 的发送方式。** AIPerf 把用 481 聊天模板渲染好的完整提示串作为一条 user 消息发送，服务端会再套一层模板。两臂完全相同，所以 J5 的比值可以用来对比；但它不代表真实 agent 请求的绝对速度。在 STAGE2_RESULT 的 J5 处注明。
- **LC1 的输出可能偏短。** 真实 agent 的下一步通常是发出一次工具调用。如果某次生成不足 128 token，按规则不计入并标注，**不要因此重跑**。

---

## 三、阶段 2 的新顺序（取代手册 2.2、2.3、2.6 的顺序部分，判据不变）

**为什么要调整顺序。** T16 的独审文件必须绑定 dry-run 回执，而 dry-run 只有在**没有任何 `ft serve` 运行时**才能通过（基础工装的 ps 扫描）。如果按原顺序先跑 T16，GPU 就要空着等独审。改为：停 481 → 两次 dry-run → **马上开始 hybrid** → 主会话在 hybrid 运行期间做独审 → T16 → 恢复。

另外，D09fix 改为先跑：它的工装与 batch163 验证过的那套最接近，D05 这套是新改的。

### S0：CPU 修改（现在就做，481 继续运行）

1. **S0-1：** 按 2.1 修改 D05 的 runner 并测试。
2. **S0-2：** 按 2.5 重建 hybrid 准入（LC2 按 2.2 保持排除）。
3. **S0-3：** 按 2.4 修改 restore08 并重新签名。

每项完成后各写一行协调日志。三项全部完成后，写一行"S0 完成"，附上新的 SHA。
**失败处理：** S0-1 失败，按 2.1 的失败处理执行；S0-2 或 S0-3 失败，**不进入 S1**，停下来报告（没有恢复包或 hybrid 准入，不能停 481）。

### S1：停止 481（不早于 09:00，并且 S0 已完成）

1. 用 ps 确认 111553、111554 两个观察进程已经自行退出，并且 `runs/production/RESTORE481-MORNING-20261011-07/overnight_observation/` 下已经写出结果文件。如果还在运行，等待；不要 kill。
2. 执行 `ssh 9 'env | grep -E "^(FREETOKEN_|FT_)" | wc -l'`，结果必须为 0。
3. 执行 STAGE1_SUMMARY 第 3.1 节的停止命令（restore07 包的 `stop_approved_restore.py`），然后按手册 2.6 核对三项。

### S2：两次 dry-run（只用 CPU，大约 2 分钟）

```bash
ssh 9 'cd /data2/FreeToken && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B /data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/owned_launch.py --dry-run --card D09FIX'
ssh 9 'cd /data2/FreeToken && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B /data2/FreeToken/development/kimi_phase2_20261011/t16_d05/owned_launch.py --dry-run --card D05'
```

- 成功：`runs/dev_T16/reviews/` 下生成 `<rid>_file_dry_run_v2.json`。
- 在协调日志写一行：`S2 完成，等待主会话独审`，附上两个回执的 SHA256。
- **失败处理：** 哪一个失败，就取消那一项的 T16（本窗口内不修），记录原因后继续 S3。

### S3：hybrid 验证（**不等独审，S2 完成后立即开始**）

按 STAGE1_SUMMARY 第 3.4 节的命令执行，`--admission` 指向 S0-2 重建后的准入。判据和失败处理与手册 2.4、2.7 相同。

### S4：T16（hybrid 结束之后）

1. **检查独审和批准文件。** 下面 4 个文件由**主会话**写入，KIMI 不能自己写：
   - `runs/dev_T16/reviews/E2-D09FIX-T16-20261011_startup_review_v2.json`
   - `runs/dev_T16/reviews/E2-D09FIX-T16-20261011_user_scope_approval_v1.json`
   - `runs/dev_T16/reviews/E2-D05-T16-20261011_startup_review_v2.json`
   - `runs/dev_T16/reviews/E2-D05-T16-20261011_user_scope_approval_v1.json`

   这些文件都必须是 0444。
2. **哪一项的两个文件都齐了，就跑哪一项。** 先跑 D09fix，再跑 D05，命令见 STAGE1_SUMMARY 第 3.3 和 3.2 节（`--run`）。
3. **如果 hybrid 结束时一个文件都还没有：** 每 5 分钟检查一次，最多等 30 分钟，每次检查都写日志。30 分钟后仍然没有，就跳过 T16，进入 S5。T16 改到晚上的窗口再跑。
4. **分支规则：**
   - D09fix 结果为 failed_harness：跳过 D05，因为两套工装同源；
   - D09fix 结果为 not_met 或 kept：继续跑 D05；
   - D05 结果为 failed_harness：记录后进入 S5。

### S5：恢复 481

按 STAGE1_SUMMARY 第 3.5 节分三步执行（restore08）。失败时按该节的回滚命令处理。恢复时间晚于 18:30 的情况，见 2.4 的补充规则。

### S6：写结果报告

按手册 2.8 撰写 `STAGE2_RESULT.md`，并写明 S2 的回执、独审文件和批准文件的 SHA。

### 时间预估（压力测试，主会话已告知用户）

| 段 | 时间 |
|---|---|
| S0 | 09:00–09:30（481 照常服务） |
| S1–S2 | 约 09:30–09:40，481 从这时开始停止服务 |
| S3 | 约 09:40–11:20（上限 12:10） |
| S4 | 约 11:20–13:20（两次 T16，各约 1 小时） |
| S5 | 约 13:20–13:40 |

481 预计停服约 4 小时（最长约 5 小时）。hybrid 运行期间约 21 个 CPU 核满载，累计约 40 分钟。

---

## 四、审核依据（主会话核实记录）

- D05 环境变量与默认关闭路径：`wt/d05-decode-align-481-20261011` 对 481d3a7 的 diff（env.py:81、scheduler.py:1153–1160、cache.py `snapshot_decode_alignment`）。
- 基础工装 `t16_private_port_dryrun_r062_v1.py:186–197` 的 `environment()` 只清除 `FT_DEV_`/`FT_D3_`；`strict_args`（66–86 行）在 `allowed_new` 为空时拒绝一切增量。
- D09fix：`git diff bd57..7d8d389e --stat` 只涉及 `scheduler/cache.py` 和 `tests/scheduler/test_hybrid_cache_manager.py`。
- T16 控制器：`require_leaf_review` 绑定源文件 SHA 和 dry-run 回执 SHA；`require_user_scope_approval` 只绑定固定字段（rid、两个提交号、arms=8、calls=100、queue_predecessors、approved）。
- `G_seed12k/round-01` 第 1 条消息：20,117 字符，173 个非空行中 168 行完全相同。
- restore08：`require_root_final_review` 不检查 `independent_review_sha256`。这个字段只是审计记录，但仍按 2.4 填写。`observe_overnight.py:34` 要求截止时间在未来。
- hybrid 工装：服务环境显式设置 `CUDA_VISIBLE_DEVICES='0'`（`hybrid_service.py:190`）；前置检查不依赖 T16 是否已完成（`gpu_window.py:77–118`），所以 S3 可以排在 S4 之前。
