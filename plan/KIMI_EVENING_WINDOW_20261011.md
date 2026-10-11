# KIMI 晚间窗口指令（2026-10-11，主会话）

- **依据**：`development/kimi_phase2_20261011/STAGE2_RESULT.md`（SHA `0e7f299a…eaa64`），以及主会话 10:00–10:10 在服务器上的复核与修复验证（见第 2 节）。
- **适用范围**：本文取代 `plan/KIMI_STAGE1_REVIEW_20261011.md` 第三节的阶段 2 顺序和失败路由。该文件中的其余裁定继续有效：LC2 取消、测试端点 127.0.0.1:8123、J1–J5 判据、T16 判据、LC1 附注。
- **红线不变**：不推送；不启动 Ollama；不改论文；不删、不改旧证据；不删 GPU 锁；任何一步都不重试。
- **执行方式**：拿不准就停下，在协调日志里写明原因，等主会话处理。
- **本文件发出后即冻结，不再修改。** restore09 的独审字段绑定的是本文件的 SHA；以后如需更正，另发补充文件。

---

## 0. 结论

1. **S3 的根因属实，主会话已在服务器上独立复现。**
   - 主控 `gpu_window.py` 把窗口截止时间原样交给服务。
   - 服务 `hybrid_service.py:162` 要求收到的截止时间不晚于"窗口截止 − 60 s"，两者相比恒为真，所以必然中止。
   - 来历：retry2 的主控交给服务的是预留过的子截止时间（如 `min(deadline-1200, now+900)`）。新主控删掉了恢复职责，交接时却改成传原值，服务端检查保持不变。
2. **S4 被跳过，是主会话指令的问题，不是 KIMI 执行的问题。**
   - 审核文件 S3 写的是"失败处理与手册 2.7 相同"，而 2.7 规定"工装报错 → 跳到恢复"。
   - 这条规则原本是为 hybrid 排在最后的旧顺序写的。主会话把 hybrid 提到 T16 之前时，没有重新核对它，结果 hybrid 一失败，就连带取消了与它互不依赖的 T16。
   - KIMI 按字面执行，是对的。
3. **更正 STAGE2_RESULT 中的一处表述。** 报告说"26 项测试覆盖了该函数，但用的是合成事件"。实际上没有任何测试走到截止检查：唯一涉及 `require_master_context` 的测试（`test_direct_import_cannot_start_service_component`）在函数第一项入口检查处就返回了。
4. **今晚的窗口没有任何步骤需要等主会话。**
   - T16 的 4 份独审/批准文件已在 10:05 写好并封存（第 5 节）。
   - E0 的验收全部是机械检查。
   - restore09 的独审依据就是本文件（做法与 restore08 相同）。

## 1. 主会话复盘：本次三处失误

| # | 失误 | 后果 | 改进（本文已落实） |
|---|---|---|---|
| 1 | 阶段 1 审核时，把"pytest 26 过 + PIN_AND_ARGV_GATE_PASS"当成工装就绪的证据，没有核对真实入口（`gpu_window` → `hybrid_service`）有没有被执行过。真实入口要求生产已停，因此 CPU 测试从未走过主控到服务的交接 | 停服 13 分钟，什么都没测到；晚间还要再停一次 | 凡是要占用停服窗口的工装，窗口前必须做**真实入口演练**：用真实代码和真实准入，只替换"生产已停"才能满足的几项，一直跑到取 GPU 锁之前；同时必须有**反向对照**，证明演练抓得住已知缺陷（E0-3） |
| 2 | 调整步骤顺序后，没有重新核对失败路由 | hybrid 失败时连带取消了 T16 | 第 4 节为每一步单独写明失败后去哪一步，并写明会取消、不会取消哪些后续步骤 |
| 3 | T16 独审文件要等"用户看到日志后转告主会话"才写，这条人工转达链放在了停服窗口的关键路径上 | 即使 hybrid 成功，T16 也可能因为文件没就位而跳过 | 4 份文件已提前封存，晚间窗口不依赖任何人工转达 |

## 2. 下发前自检（逐条附核算）

| 项 | 核算或证据 |
|---|---|
| 演练能抓住上午的缺陷 | 演练脚本（`hybrid_verify/rehearse_master_entry.py`，SHA `3443d4b0…37270`）在**当前未修复**的工装和准入上运行：2 ms 内被同一条错误拒绝；481 照常服务；协调日志未被写入。回执：`runs/dev_hybrid_verify_20261011/rehearsal_mainsession_A_currentcode/REHEARSAL_RECEIPT.json`（SHA `e5fe7149…24eb`） |
| 修复有效 | 在副本 `runs/dev_hybrid_verify_20261011/mainsession_fixcheck/hv/` 中应用修复后，演练走到 GPU 门前，7 项检查全部通过（回执 SHA `48b37adf…0d74`）。把预留改回 0，也就是上午的写法，又被拒绝（回执 SHA `51936b19…6725`） |
| 修复的前提 | 服务端要求"服务截止 ≤ 窗口截止 − 60 s"。主控改为交出"窗口截止 − 120 s"，留 60 s 余量，不依赖浮点数恰好相等。服务内部另有预留：就绪 180 s、预热 120 s、测量 60 s。9000 s 窗口内余量充足 |
| E0 指令本身可执行 | 主会话在副本 `runs/dev_hybrid_verify_20261011/mainsession_e0check/` 中，原样执行了 E0-1 至 E0-3 的命令，结果如下：<br>• `gpu_window.py` 的 SHA = `244ef9dd…`；<br>• `diff_prepare_admission.txt` 只有两行常量的改动；<br>• 准入构建 pytest 26 passed，`baseline_owner.approval_id` = -08，`output_root` = window02；<br>• `offload_argv`、`hybrid_argv`、`services`、`service_order` 和生产启动参数都与 window01 相同；<br>• 两次演练都 PASS（回执 SHA `eefe4545…c3dc`、`d94a090b…493e`）。<br>副本中的 `inputs` 和 `output_compare_path` 与 window01 不同，只是因为副本换了目录；在正式目录 HV 中它们必须相同。E0-4（restore09）沿用 restore08 的同一流程，主会话没有预演 |
| 准入基线 | `prepare_root_admission.py` 中写死了 `EXPECTED_APPROVAL = -07`，而 -07 已经不在运行，不改的话重建时会直接报错。新准入必须冻结 -08 的生产记录；窗口的前置检查会据此核对 -08 的进程，以及 -08 的观察器 |
| 输出目录 | `window01` 里存着上午的证据，而主控要求输出目录事先不存在，所以新准入改用 `window02` |
| 演练覆盖不到的部分（取锁之后），已做静态核对 | ① offload 服务日志里有 `moe_cache_size=2700`（-08 的 serve.log 实测），解析不会因为 offload 报错。② 上下文长度：LC1 87,328 + 外壳约 10 + 生成 256 ≈ 87.6K，小于 `--max-seq-len-override 98304`。③ hybrid 只改变解码路径（`offload_cache.py:146`、`layers/moe.py:305`），预填与 offload 走同一条路径。retry2 中 1.2K 提示的 TTFT：hybrid 3.65 s，offload 3.96 s。据此**推算** 87K 的预填远低于 LC1 单项 900 s 的超时，但这一点**未在 87K 上实测** |
| 残余风险 | 同一个服务内，任何一项测量失败，都会结束该服务剩下的测量，包括排在后面的 quality60。如果 H1 的 LC1 失败，本窗口就拿不到 hybrid 的 J2，只能下次补测。不为此改代码，因为改代码就会引入新的、没有演练过的路径 |
| 时间 | T16 每次约 1 h。hybrid 预计约 90 min（O1 约 35、H1 约 37、H2 约 6、O2 约 12），上限 150 min。恢复约 15 min。预计 19:05 停服，约 23:10 恢复；最坏约 01:00 |
| 顺序：T16 在前 | T16 已有真实路径 dry-run 回执，治理文件齐全，确定性高。hybrid 取锁之后仍有残余风险，而它一旦"清理失败、锁未释放"，会中止窗口；排在前面就会挡住 T16 |
| 压力测试告知 | 已在主会话给用户的回复中说明：两次 T16，hybrid 约 21 核满载累计约 40 分钟，481 停服约 4 小时 |
| CPU 与 GPU 不并行 | E0 全部在 481 服务期间完成，不涉及计时；窗口内不跑 CPU 重任务 |

---

## 3. E0：现在开始，纯 CPU（481 继续服务），18:30 前完成

工作目录：`/data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify/`（下称 HV）。服务器上的文件都是 0444，所以先把旧件移走，再放新件；不要用 chmod 改写旧件。

### E0-1 hybrid 修复（只改 `gpu_window.py`）

```bash
HV=/data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify   # 以下 E0 各段都在同一个 shell 中执行
cd $HV && mkdir _superseded_window01
mv gpu_window.py ROOT_ADMISSION.json ADMISSION_BUILD.json BASELINE_OWNER_FREEZE.json prepare_root_admission.py _superseded_window01/
cp /data2/FreeToken/runs/dev_hybrid_verify_20261011/mainsession_fixcheck/hv/gpu_window.py gpu_window.py && chmod 0444 gpu_window.py
diff -u _superseded_window01/gpu_window.py gpu_window.py > diff_gpu_window_fix.txt
```

**验收：**
- `sha256sum gpu_window.py` 等于 `244ef9dd4a212d1bdc45133c5cbb957209d975bafac80c3d7a4784af8454a39c`。
- `diff_gpu_window_fix.txt` 只有两处改动：
  - 在 `CONTROLLER_FILES` 之后新增 3 行（2 行注释，加上 `SERVICE_RESERVE_SECONDS = 120`）；
  - 把 `run_service(path, label, deadline)` 改为 `run_service(path, label, deadline - SERVICE_RESERVE_SECONDS)`。
- 另外三个控制器文件保持不变：`hybrid_service.py` 的 SHA 仍为 `f1d488a3…5b00`，`window_measure.py` 与 `warmup_client.py` 的 SHA 与 window01 准入中的钉值一致。

**失败处理：** 今晚取消 hybrid，T16 不受影响；记录后继续 E0-4。

### E0-2 准入重建

```bash
cd $HV && sed -e "s/^EXPECTED_APPROVAL = 'RESTORE481-MORNING-20261011-07'$/EXPECTED_APPROVAL = 'RESTORE481-MORNING-20261011-08'/" \
  -e "s#^OUTPUT_ROOT = '/data2/FreeToken/runs/dev_hybrid_verify_20261011/window01'\$#OUTPUT_ROOT = '/data2/FreeToken/runs/dev_hybrid_verify_20261011/window02'#" \
  _superseded_window01/prepare_root_admission.py > prepare_root_admission.py && chmod 0444 prepare_root_admission.py
diff -u _superseded_window01/prepare_root_admission.py prepare_root_admission.py > diff_prepare_admission.txt
```

然后用阶段 1 的同一条构建命令重建准入，再运行准入回读门。

**验收：**
1. `diff_prepare_admission.txt` 只有上面两行常量的改动。
2. 构建回执里：pytest 26 passed；两条参数解析器 dry-run 都输出 `PARSE_OK`。
3. 新的 `ROOT_ADMISSION.json` 是 0444，并满足以下全部条件：
   - `window_limit_seconds` = 9000；
   - `output_root` 以 `/window02` 结尾；
   - `host`/`port` = 127.0.0.1/8123；
   - `baseline_owner.approval_id` = `RESTORE481-MORNING-20261011-08`；
   - `controller_source_pins` 中 `gpu_window.py` 的值 = `244ef9dd…a39c`；
   - `hybrid_controller_sha256` = `f1d488a3…5b00`。
4. 与 `_superseded_window01/ROOT_ADMISSION.json` 逐字段比较，**只允许**以下字段不同：`recorded_at`、`baseline_owner`、`baseline_owner_freeze_sha256`、`output_root`、`controller_source_pins`。特别要确认 `offload_argv`、`hybrid_argv`、`services`、`service_order`、`inputs` 完全相同，也就是 -08 与 -07 的生产启动参数一致。
5. 回读门输出 `PIN_AND_ARGV_GATE_PASS`。

**失败处理：** 今晚取消 hybrid；继续 E0-4。

### E0-3 真实入口演练（脚本由主会话提供，KIMI 只运行，不修改）

```bash
cd $HV
/data2/FreeToken/venv/bin/python -B rehearse_master_entry.py --admission ROOT_ADMISSION.json \
  --out-dir /data2/FreeToken/runs/dev_hybrid_verify_20261011/rehearsal_window02_gate --expect reach_gpu_gate
/data2/FreeToken/venv/bin/python -B rehearse_master_entry.py --admission ROOT_ADMISSION.json \
  --out-dir /data2/FreeToken/runs/dev_hybrid_verify_20261011/rehearsal_window02_negctl --expect deadline_reject --reserve-override 0
```

**验收：**
- 两条命令都打印 `REHEARSAL PASS …`，退出码均为 0。
- 两份 `REHEARSAL_RECEIPT.json` 中的 `source_admission_sha256` 都等于新准入的 SHA。

**演练做了什么：**
- 用真实代码执行一份准入副本。这份副本与正式准入只差 `output_root`。
- 只替换四项，都是 481 在服务期间无法满足的：
  - 生产停服前置检查；
  - 协调日志行改写到演练目录；
  - `__main__` 入口标识；
  - `idle()`，即取 GPU 锁之前的最后一步。
- 第一条命令证明修复后能走到 GPU 门前。第二条是反向对照，证明演练能看见上午的那类缺陷。

**失败处理：** 今晚取消 hybrid，不修改代码，记录后继续 E0-4。

### E0-4 restore09（晚间恢复包，**今晚开窗的硬前提**）

- 从 restore08 复制出 restore09，只做身份替换。
  - 编号 `RESTORE481-MORNING-20261011-08` 改为 `-09`。这是系列编号，不表示时段；保持原有格式，可以让 diff 只剩一处纯粹的 08→09 替换。
  - `run_dir` 相应改为 -09。
- `observation_until` 改为 `2026-10-12T09:00:00+08:00`，即观察器运行到明早 9 点。
- 重新签署 `approval_sha256`。
- `ROOT_FINAL_REVIEW.json` 中：
  - `independent_review_sha256` = **本文件**的 SHA256：先把本文件 scp 到服务器 `/data2/FreeToken/plan/`，确认与本地副本 SHA 相同后再填；
  - `pending_independent_review` = false。
- 两侧 pytest 7 过，加上 `GATE_CHAIN_PASS`；全部文件 0444 封存。
- 输出 `diff_restore09.txt`（与 restore08 对比）。

**验收：** diff 只允许包含以下内容：08→09 的身份字符串、`observation_until`、`approval_sha256`，以及 ROOT_FINAL_REVIEW 的两个字段。出现任何其他差异，E0-4 即判为失败。

**失败处理：** 今晚**整个窗口取消**，不停 481。理由：没有恢复包，就不能停服。

### E0-5 完成记录

- 协调日志写一行"E0 完成"，附 E0-1 至 E0-4 的结果和全部新 SHA。
- 写完后**不需要等主会话**。

**否决机制：** 18:55 时检查本地 `plan/KIMI_EVENING_STOP.md` 和服务器 `/data2/FreeToken/plan/KIMI_EVENING_STOP.md`。只要其中任何一个存在，就不开窗，按文件内容处理。主会话复核 E0 时如果发现问题，会写这个文件。

---

## 4. 晚间窗口 E1–E6

### E1 开窗条件与停 481

18:55 起逐项检查。全部满足后才停服：

1. E0-4 通过。E0-1 至 E0-3 如果失败，只取消 hybrid。
2. 不存在 STOP 文件。
3. 当前时间 ≥ 19:00，且 -08 观察器已自行退出（`runs/production/RESTORE481-MORNING-20261011-08/overnight_observation/terminal.json` 已写出）。如果 19:15 还没退出，不要 kill，不开窗，记录并回报。
4. `env | grep -E "^(FREETOKEN_|FT_)" | wc -l` 的结果为 0。

停服命令：

```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```

**成功判据：**
- 退出码 0；
- 存在 `runs/production/RESTORE481-MORNING-20261011-08/stopped.json`；
- `production.active.json` 已移除；
- `gpu.lock` 已释放；
- `nvidia-smi` 中没有计算进程。

**失败处理：** 不做后续任何一步，按手册 2.7 的清理规则处理，然后回报。

### E2–E5 命令

| 步 | 命令 | 判据 |
|---|---|---|
| E2 T16 D09fix | STAGE1_SUMMARY 3.3 的"正式执行"命令（`owned_launch.py --run --card D09FIX`）。**不再做 dry-run**：回执和治理文件都已就位，启动器会自行校验 | 开关关闭时，所有臂的 sequence 和 h2d 都 SAME（kept），否则记 not_met |
| E3 T16 D05 | STAGE1_SUMMARY 3.2 的"正式执行"命令（`--run --card D05`） | 同上 |
| E4 hybrid | STAGE1_SUMMARY 3.4 的命令，`--admission` 指向 E0-2 重建后的 `ROOT_ADMISSION.json`。**最晚 22:00 开始** | J1–J5 由工装机械判定 |
| E5 恢复 481 | STAGE1_SUMMARY 3.5 的三步，把路径里的 restore08 换成 restore09，`run_dir` 换成 -09 | 冒烟 `exit_code=0`；df77cb 基准逐字段一致；观察器运行到 2026-10-12 09:00 |

### 失败路由（每一步单独规定；所有步骤都不重试）

| 情况 | 去向 | 会取消哪些步骤 |
|---|---|---|
| E2 结果为 kept 或 not_met | E3 | 无 |
| E2 结果为 failed_harness | 跳过 E3，去 E4 | 只取消 E3（两套工装同源） |
| E3 出现任何结果 | E4 | 无 |
| E0-1 至 E0-3 有任何一项失败 | 跳过 E4，去 E5 | 只取消 E4 |
| 到 22:00 时 E4 还没开始 | 跳过 E4，去 E5 | 只取消 E4 |
| E4 中某个服务测量失败 | 工装自动继续下一个服务；窗口结束后去 E5 | 只影响该服务剩下的测量 |
| E4 出现 window_error（包括前置检查失败） | 去 E5 | 无 |
| 任何一步出现清理失败，或 GPU 锁未释放 | 轮询等待 120 s；仍然失败，就写 `CLEANUP_BLOCKED.md`，跳过剩下的所有 GPU 步骤，去 E5 | 剩下的全部 GPU 步骤 |
| E5 失败 | 走 STAGE1_SUMMARY 3.5 的回滚流程（restore09 包）；回滚也失败，就写 `PRODUCTION_DOWN.md`，在协调日志中标"紧急" | 无 |

**时间线（预计）：**

| 时间 | 事项 |
|---|---|
| 19:05 | 停服 |
| 19:10–20:10 | E2 |
| 20:15–21:15 | E3 |
| 21:20–22:50 | E4 |
| 22:55–23:10 | E5 |

481 预计停服约 4 小时，最坏情况到 01:00 左右。

### E6 结果报告

写 `development/kimi_phase2_20261011/EVENING_RESULT.md`，内容包括：

- 每一步的终态；
- 两次 T16 的判定和 round 编号；
- hybrid：直接引用 `verdict.json` 的 J1–J5 表，以及各服务的 `terminal.json` 状态；
- 恢复冒烟结果；
- 证据的 SHA 索引；
- 与本文不一致的任何地方（如果有）。

协调日志写"晚间窗口结束，等主会话复核"。

---

## 5. 已就位的治理文件（主会话写入并封存，KIMI 只读）

位置：`/data2/FreeToken/runs/dev_T16/reviews/`。已逐一用启动器自身的 `require_leaf_review` 和 `require_user_scope_approval` 校验通过。

| 文件 | SHA256 |
|---|---|
| `E2-D09FIX-T16-20261011_startup_review_v2.json` | `23e9b696ad2685894689d4f394f57244231f48032937837843d1d8f4868f0765` |
| `E2-D09FIX-T16-20261011_user_scope_approval_v1.json` | `f75489e197e52fd2df4e00a2be2380d8b9e3cacef75625f5e3b2933091ec1427` |
| `E2-D05-T16-20261011_startup_review_v2.json` | `ae940f2febadafa45786b7df80a1f85167708a19c08ea8f9aa210066d63adb3f` |
| `E2-D05-T16-20261011_user_scope_approval_v1.json` | `30ad89695889ca0758bec978f5e1aecbe1d9e5e78a4c624db6af2486de24795c` |

- 两份批准文件在 10:06 改写过一次。原因：用户裁定的日期误写成 UTC 日期，改正为 2026-10-11 02:12 +08:00。改写发生在任何程序读取它们之前。
- **冻结要求**：从现在到 E3 结束，`t16_d05/`、`t16_d09fix/`、`runs/dev_T16/reviews/` 中的任何字节都不得改动。一旦改动，绑定就失效，启动器会拒绝启动；这是安全的失败方式，但今晚的 T16 也就跑不成了。

## 6. 主会话后续

- 用户转告"E0 完成"后，主会话复核 E0。发现问题就写 STOP 文件；没问题就不写，不需要回复。
- 用户转告"晚间窗口结束"后，主会话复核 EVENING_RESULT.md。
