# op-hak 任务 A 补充 1 执行记录（CPU 阶段，2026-10-11 夜）

- 依据：`plan/OPHAK_TASK_A_ADDENDUM1_20261011.md`，SHA256 `7b9464580e4a3d8e63a1b7a217960b333ede87a07c100f8f02f458a21fa99caa`（两侧一致，0444）。
- 放行：协调日志 20:53:17，主会话（freetoken-06）写"任务 A 放行（用户确认）"。
- 本文件只记录补充 1 第 3、4 节的改动。`CPU_READINESS.md` 未改动（仍为 0444）。原指令其他条目不变。

## 1. 第 3 节：W0 第 2 条改写

| | 改动前 | 改动后 |
|---|---|---|
| 工装 | `task_a_runner.py` SHA `f0210979b38721c1…` | `task_a_runner.py` SHA `96713dcef4d4c55e…` |
| W0 第 2 条 | 协调日志有 D11-P0 终态行（`TERMINAL_LINE_RE`），且 `stall_probe` 为空 | `d11p0_not_running`：`stall_probe` 为空，且 `runs/` 下名称含 `d11_p0` 的顶层目录在最近 600 秒内没有文件更新（没有这类目录即满足） |
| 实现 | `TERMINAL_LINE_RE`、`gemini_d11p0_terminal_line` | 删除 `TERMINAL_LINE_RE`；新增 `latest_mtime`、`active_d11p0_dirs`（常量 `D11P0_QUIET_S = 600`）；`w0_checks` 中对应项改为 `d11p0_not_running` |

- 只改这一处。W0 的其他条目（主会话放行行、STOP 文件、环境变量、481 在 -10 上 serving、GPU 锁属于生产、无 D09 窗口进程）不变。
- 单测：`test_task_a_runner.py` SHA `548488a02d6e2020…`，**20 passed**（原 18 项；新增 2 项覆盖新检查：只计最近 10 分钟内有更新的 d11_p0 目录；目录不存在时通过）。
- W3 前复查：执行 W3 停 481 之前再查一次 `pgrep -f stall_probe.py`（工装内为 `stall_probe.py` 进程的 argv 匹配）。非空则不停 481，协调日志写"任务 A 与 D11-P0 冲突"，等主会话。
- 注意：`REHEARSAL.json` 的 `sources` 记录的是改动前的 `task_a_runner.py`（`f0210979…`）。本次改动只涉及 W0 检查函数，演练路径（请求、解析、窗口编排、OOM、清理）未调用它，代码未变。

## 2. 第 4 节：restore11（取代 H3 的 restore12）

- 构建脚本：`build_restore11.py`（SHA `cb77b6abbe933092…`），由 `build_restore12.py` 派生：只改常量与身份文字，流程相同。diff 输出改为 `diff_restore11.txt`，避免覆盖 H3 的 `diff_restore12.txt`。
- 替换：只替换两个精确字符串，`RESTORE481-MORNING-20261011-10` → `-11`，`ROLLBACK184-MORNING-20261011-10` → `-11`。`run_dir` = `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11`。
- 独审字段：`independent_review_sha256` = `7b9464580e4a3d8e63a1b7a217960b333ede87a07c100f8f02f458a21fa99caa`（本补充文件）。
- 各项 SHA256：
  - `restore11/DEPLOYMENT_APPROVAL.json` `c8fb07f3abcc…`
  - `restore11/SOURCE_MANIFEST.json` `ad41896091cd…`
  - `restore11/ROOT_FINAL_REVIEW.json` `01bc3861de23…`
  - `diff_restore11.txt` `e90b511d9677…`（131 行，与 restore12 的 diff 同类）
- 验证：
  - `pytest test_cpu_orchestration.py`：**7 passed**；
  - 门链：`GATE_CHAIN_PASS RESTORE481-MORNING-20261011-11 2026-10-12T09:00:00+08:00`。
- diff 只含允许类别：两处身份字符串、`run_dir`、`rollback_approval`、重算的哈希、README 与 scope 的身份说明；另有模板中排除的两项（`Only in restore10`）。
- **restore12 已由 restore11 取代。** restore12 原样保留、不再使用、未修改：`restore12/DEPLOYMENT_APPROVAL.json` `cd09c4bd4dee…`，`restore12/ROOT_FINAL_REVIEW.json` `a05f4de8cad8…`。
- 模板 `restore10/DEPLOYMENT_APPROVAL.json` 的 SHA 仍为 `16529ccb4e09…`，未被改动。
- W5 前检查：`/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11` 不存在（已核对）。若届时已存在，停下等主会话，不改用 -12。

## 3. 证据位置

- 服务器 WORK：`/data2/FreeToken/development/ophak_task_a_20261011/`（含 `restore11/`、`diff_restore11.txt`、`build_restore11.py`、`task_a_runner.py`、`test_task_a_runner.py`）。
- 本地镜像：`D:\00.开发\2026\03-模型实验\freetoken\freetoken\development\ophak_task_a_20261011\`。
