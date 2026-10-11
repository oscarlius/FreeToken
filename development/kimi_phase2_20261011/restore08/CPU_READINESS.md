# restore08 CPU 就绪报告（手册 1.4b：停止与恢复 481）

构建时间：2026-10-11 上午（阶段 1，纯 CPU，未执行任何停止/启动）。目录：`/data2/FreeToken/development/kimi_phase2_20261011/restore08/`（本地同名镜像）。原目录 `development/morning_restore07_20261011/` 未改动。

## 0. 关键分工：停止用 restore07，恢复用 restore08

停止的是**当前正在运行的生产 -07**：`stop_approved_restore.py` 内置"拒绝停止外来 owner"检查（`production.active.json` 的 approval_id 必须等于本包审批号），因此停止命令必须用**原 restore07 包**（审批 -07），不能用 restore08。restore08（审批 -08）只承担阶段 2 最后一步的**恢复**（启动 + SDK 冒烟 + df77cb 对比 + 失败回滚）。

## 1. 停止命令（阶段 2 第一步；现在不执行）

```bash
ssh 9 'cd /data2/FreeToken/development/morning_restore07_20261011 && \
  /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```

- 内部行为：校验 restore07 包的 ROOT_FINAL_REVIEW 链 → 核对 `production.active.json` 的 owner 是 `RESTORE481-MORNING-20261011-07`、commit 是 481d3a7 → 调用冻结控制器 `release_control.py --stop --approval-id RESTORE481-MORNING-20261011-07` → 要求 `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-07/stopped.json` 出现。
- 预期输出：冻结控制器打印停止进度，进程退出码 0；`stopped.json` 存在；`production.active.json` 被控制器移除；GPU 锁释放。退出码非 0 或缺 `stopped.json` 即失败——**失败处理：不重试**，按手册停下记录。
- 前置：观察窗口 09:00 已结束（`post_night_observer`/`observe_overnight` 已自行退出）。若 09:00 后观察进程仍在，**不要 kill**，停下等它或请示主会话。

## 2. 恢复命令（阶段 2 最后一步；restore08）

按 retry2 已验证的恢复路径，分步执行（不要用 `deploy_conditional.py --execute`：它末尾的观察器会阻塞到次日 09:00）：

```bash
# 1) 启动（内含全部 preflight：工作树/原生扩展清单、GPU 空闲、8095/8096 无监听、无锁、run_dir 不存在）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  /data2/FreeToken/venv/bin/python start_approved_release.py'

# 2) 等待 serving 并执行 SDK 冒烟（内含 df77cb 基准的 15 个稳定字段与启动参数逐项对比）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py'

# 3) 冒烟通过后启动任务观察器（后台脱离，不阻塞）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-08/observer_outer.log 2>&1'
```

- 第 1 步预期：打印 JSON `{"status": "started_waiting_serving", ...}`，`owner.json` 出现在新 run_dir。
- 第 2 步预期：等待 `/health` 报 serving（最长 1800 秒）→ 调用冻结 `run_smoke.py`（SDK 短 512 / 长 8257 各 128 token）→ 与 df77cb 基准（`first_cold_baseline`，SHA 钉在审批中）逐项对比 → 写 `smoke_execution_result.json`，`exit_code=0` 且 `classification="passed"` 为通过。
- 第 3 步预期：观察器以 `--until 2026-10-12T09:00:00+08:00` 运行（**此值是本次新设的身份/策略值，待审核**；-07 用的是当天 09:00）。
- 全部一致才算恢复成功（手册 2.5）。

## 3. 回滚命令（启动或冒烟失败时；恢复被审查的 stop-before-rollback184 逻辑）

```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  /data2/FreeToken/venv/bin/python -c "import subprocess; from deploy_conditional import recover_after_restore_failure; raise SystemExit(recover_after_restore_failure(subprocess.run))"'
```

行为：先记失败回执（不得冒称冒烟）→ `stop_approved_restore.py`（本包，停 -08）→ 停成功后 `start_approved_rollback.py`（ROLLBACK184-MORNING-20261011-08）→ `wait_rollback_and_smoke.py`。停止失败则**不启动回滚**（门设计如此）。任一步非 0 即失败：不重试，按手册"恢复失败"类停下并记录。

## 4. 与 restore07 的 diff（`diff -ru` 全文：`kimi_phase2_20261011/diff_restore08.txt`）

仅 6 个文件有差异，全部是身份信息：

| 文件 | 改动 |
|---|---|
| DEPLOYMENT_APPROVAL.json | approval_id/rollback_approval/run_dir -07→-08；package_source_manifest_sha256 同步为新清单 SHA `f062ca46…6db6617`（门链要求）；recorded_at=2026-10-11T08:31:43+08:00（重签时刻）；observation_until→2026-10-12T09:00:00+08:00（待审核）；scope 两条身份串；user_authority 改指手册阶段 2 |
| observe_overnight.py | 第 37 行审批号 -07→-08 |
| test_cpu_orchestration.py | 测试夹具中的审批号/回滚号/run_dir -07→-08 |
| SOURCE_MANIFEST.json | 上述两 .py 的新 SHA；package 字段改为 kimi_phase2_20261011/restore08 |
| ROOT_FINAL_REVIEW.json | approval_id -08；approval_sha256=`df254840…a288ec654`；package_source_manifest_sha256=`f062ca46…6db6617`；recorded_at=2026-10-11T08:31:43+08:00；independent_review_sha256=null、pending_independent_review=true（**本次由工装生成，待主会话审核**）；scope 文本 |
| README.md | 本说明 |

其余 10 个文件（含 deploy_conditional.py、stop_approved_restore.py、start_approved_release.py、run_exclusive_smoke.py、全部回滚脚本）逐字节相同。df77cb 基准（`first_cold_baseline` SHA `df77cb14…f9d97`）与冻结 ops 路径原样保留。

## 5. CPU 测试输出（CUDA 关）

- 本地：`python -B -m pytest test_cpu_orchestration.py -q` → **7 passed**。
- 服务器：`cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B -m pytest test_cpu_orchestration.py -q` → **7 passed in 0.02s**。
- 服务器门链自验（`approved_attempt.load()` 走完整 ROOT_FINAL_REVIEW + SOURCE_MANIFEST SHA 链）：**GATE_CHAIN_PASS RESTORE481-MORNING-20261011-08**。
- 构建时发现并已修正：restore07 的门会把审批里的 `package_source_manifest_sha256` 与评审比对，换身份后必须同步该字段（已改，见上表）。
- 终验时发现并已修正（修复 2）：observe_overnight.py 与 test_cpu_orchestration.py 曾因 Windows `write_text` 默认换行转换被写成 CRLF，导致与 restore07 的 diff 为全文件差异。已改回 LF（仅身份行差异，见 `diff_restore08.txt`），并按门链顺序重签：SOURCE_MANIFEST.json `files{}` → DEPLOYMENT_APPROVAL.json `package_source_manifest_sha256` → ROOT_FINAL_REVIEW.json `approval_sha256`。重签后本地与服务器两侧 pytest 7 passed、`GATE_CHAIN_PASS RESTORE481-MORNING-20261011-08` 均复核通过，四个关键文件 SHA 两侧一致。

## 6. 注意

- restore08 的审批要求 `run_dir` 不存在、GPU 无计算进程、8095/8096 无监听、无 GPU 锁——即只能在 481 已停且 T16/hybrid 窗口清理干净之后执行，与手册顺序一致。
- 若主会话不批准 observation_until 的新值，只改 DEPLOYMENT_APPROVAL.json 该字段后需同步重算 approval_sha256、ROOT_FINAL_REVIEW.json（SOURCE_MANIFEST 不含 json，不受影响）。

## 7. 修订 v2（2026-10-11 09:10，按主会话审核 `plan/KIMI_STAGE1_REVIEW_20261011.md` 第 2.4 节）

- `DEPLOYMENT_APPROVAL.json` 只改 `observation_until`：`2026-10-12T09:00:00+08:00` → **`2026-10-11T19:00:00+08:00`**（理由：避免观察进程锁住今晚的窗口；预计恢复 13:30–15:00，可观察 4–5 小时）。其余字段不变。新 approval SHA256：`4a84791cb4524723209436c8c797f63297f0eed76f7cb0c813f730002d96bb3b`。
- `ROOT_FINAL_REVIEW.json` 重签：`approval_sha256` 填新值；`independent_review_sha256` = 审核文件 SHA256 `66744c87861ee98c72a801a00a615561303fab0268ca6b31e0280cef8d9197db`（服务器那份经 scp 二进制复制，两侧 sha256sum 一致）；`pending_independent_review` → `false`；其余字段不变。新 review SHA256：`a9742ce9fe21ef0d7d6530d6c9b29c0edd851c04c9567ecb685ca7fa7798ef9a`。
- `SOURCE_MANIFEST.json` 不含 json，无需变动（仍为 `f062ca46…`）。
- 两侧复核：pytest 各 7 passed；门链 `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-08 2026-10-11T19:00:00+08:00`；两 JSON 已重新 0444 封存。
- 补充规则（审核 2.4）：若恢复晚于 18:30，`observe_overnight.py` 会拒绝启动（截止时间必须在未来），这**不算恢复失败**——只记日志"观察进程未启动（截止时间已过）"，不回滚。
