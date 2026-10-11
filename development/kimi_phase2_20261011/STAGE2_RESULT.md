# 阶段 2 结果报告（2026-10-11 上午窗口）

依据：`plan/KIMI_RUNBOOK_PHASE2_20261011.md` 第 2 节 + `plan/KIMI_STAGE1_REVIEW_20261011.md` 第三节新顺序（S0→S6）。实际执行时间 09:03–09:26，481 停服约 13 分钟（09:13–09:24，远短于预估，原因见 S3）。

## 每步终态

| 步 | 终态 | 说明 |
|---|---|---|
| S0-1 D05 runner 修订（审核 2.1） | ✅ 完成 | 参数零差异 + `FREETOKEN_D05_*` 环境清除；自检 `D05 ADAPTER SELFTEST PASS`、pytest 2 过、注入 dry-run 仍只在 ps 扫描处正确拒绝 |
| S0-2 hybrid 准入重建（审核 2.5/2.2） | ✅ 完成 | `window_limit_seconds` 6900→9000；LC2 字段无参数入口，保持原值（本窗口不跑 LC2，以审核文件为准）；pytest 26 过 ×2 + `PIN_AND_ARGV_GATE_PASS` |
| S0-3 restore08 重签（审核 2.4） | ✅ 完成 | `observation_until`→2026-10-11T19:00+08:00；门链两侧过，0444 封存 |
| S1 停 481 | ✅ 完成 | 09:13 停；观察进程已自行退出（07 观察 terminal.json 09:00 写出）；2.6 三项核对通过 |
| S2 两次 dry-run | ✅ 通过 ×2 | 回执 0444 封存（SHA 见下）；协调日志已写"S2 完成，等待主会话独审" |
| S3 hybrid 验证 | ❌ **failed_harness**（未重试） | 工装缺陷，O1 启动前中止，无任何测量；见下节 |
| S4 T16 | ⏭ 本窗口跳过 | 手册 2.7：工装报错→跳到恢复；且 4 份独审/批准文件未写（S3 即败，主会话无需再写）。两 dry-run 回执有效，T16 改晚间窗口 |
| S5 恢复 481 | ✅ 完成 | restore08 三步全过；09:24 起恢复对外服务；观察器运行至 19:00 |

## S3 failed_harness 的事实记录

- 错误：`RuntimeError('service deadline escapes the window reserve')`，在 O1 服务取 GPU 锁、起进程**之前**抛出。
- 根因（事实层面）：`hybrid_service.py:162` `require_master_context` 中 `deadline > starts[0]['deadline_epoch'] - 60`——`deadline` 与 `starts[0]['deadline_epoch']` 是同一个窗口截止值，条件恒真。阶段 1 的 26 项 CPU 测试覆盖了该函数但用的是合成事件（测试里 deadline 早于窗口截止 60s 以上），真实主控路径（主控把窗口 deadline 直接传给服务）未被演练到。
- 影响面核验：无 GPU 锁残留、无 ft serve/gpu_window 进程残留、8123 空闲、`production_stop_or_restore_attempted_by_this_tool=false`、无请求发出。窗口总耗时 0.05 秒。
- 证据（原样保留，未改动）：`runs/dev_hybrid_verify_20261011/window01/events.jsonl`（SHA `1e2297f5…ff887a`）、`terminal.json`（SHA `2fe847d2…80635a`）。
- 修复涉及 gpu_window.py / hybrid_service.py，会破准入 pins，需主会话裁定后重建准入并复验。KIMI 未自行修改。

## J1–J5

未产生任何测量（窗口在服务启动前中止），无结果表。审核附注（LC1 发送方式、输出偏短不计入）本窗口无适用对象。

## T16（本窗口未执行）

- dry-run 回执（0444，`runs/dev_T16/reviews/`）：
  - `E2-D09FIX-T16-20261011_file_dry_run_v2.json` SHA `cc458ec6e3d37594a9ff5de8d4a5b642d37e816fa28a80f30607d6811b31d3b2`
  - `E2-D05-T16-20261011_file_dry_run_v2.json` SHA `8f8efaff925bbc23680d0bee768c113dc5f1b9ad4347b8b9f389d4c4d000654e`（绑定修订 v2 runner `859b0a1c…`）
- 独审/批准文件：4 份均未写（不需要）。晚间窗口若重跑，注意回执 `timestamp` 为 09:14/09:15，独审文件绑定的是这两份回执的 SHA，不过期即可用。

## 恢复结果（S5，restore08）

- 启动：`start_approved_release.py` 退出码 0（supervisor 1205966 / service 1205996，生产 GPU 锁持有）。
- 冒烟：`wait_release_and_smoke.py` → `smoke_execution_result.json` `exit_code=0, classification=passed`（SHA `014e2165…462b0`）；`smoke_first/smoke_gate.json` 1/1 过（SHA `13e9b64a…d0a7d2`）——含 df77cb 基准 15 字段与启动参数逐项对比；`/health` 报 serving。
- 观察器：`observe_overnight.py --until 2026-10-11T19:00:00+08:00` 运行中（pid 1219625/1219627），`overnight_observation/start.json` 已写出（SHA `98f9bbe1…a2bd3`）。
- owner.json SHA `15a967f4…47e8a0`。

## 证据与 SHA 索引

| 证据 | 路径（服务器 /data2/FreeToken/） | SHA256 |
|---|---|---|
| -07 停止回执 | runs/production/RESTORE481-MORNING-20261011-07/stopped.json | `8bd90998…fe4b27` |
| -07 观察终态 | 同目录 overnight_observation/terminal.json | `192e7db7…d67940` |
| hybrid 窗口事件 | runs/dev_hybrid_verify_20261011/window01/events.jsonl | `1e2297f5…ff887a` |
| hybrid 窗口终态 | 同目录 terminal.json | `2fe847d2…80635a` |
| D09FIX dry-run 回执 | runs/dev_T16/reviews/E2-D09FIX-T16-20261011_file_dry_run_v2.json | `cc458ec6…31d3b2` |
| D05 dry-run 回执 | runs/dev_T16/reviews/E2-D05-T16-20261011_file_dry_run_v2.json | `8f8efaff…0654e` |
| -08 冒烟回执 | runs/production/RESTORE481-MORNING-20261011-08/smoke_execution_result.json | `014e2165…462b0` |
| -08 冒烟门 | 同目录 smoke_first/smoke_gate.json | `13e9b64a…d0a7d2` |
| -08 owner | 同目录 owner.json | `15a967f4…47e8a0` |
| -08 观察 start | 同目录 overnight_observation/start.json | `98f9bbe1…a2bd3` |
| hybrid 新准入（未用上） | development/kimi_phase2_20261011/hybrid_verify/ROOT_ADMISSION.json | `f874501c…3ecb0c` |
| D05 修订 runner | development/kimi_phase2_20261011/t16_d05/runner.py | `859b0a1c…c315e173` |
| restore08 审批/评审 | development/kimi_phase2_20261011/restore08/ | `4a84791c…96bb3b` / `a9742ce9…78ef9a` |

红线自检：未推送、未启动 Ollama、未改论文、未动旧证据、未删 GPU 锁、无重试；恢复后生产参数与 df77cb 基准一致。
