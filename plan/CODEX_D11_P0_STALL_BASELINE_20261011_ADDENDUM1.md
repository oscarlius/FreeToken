# 补充 1：D11-P0 放行条件第 3 条放宽（2026-10-11，主会话）

本补充针对 `plan/CODEX_D11_P0_STALL_BASELINE_20261011.md`（SHA256 前缀 7accfbe5）。原文件冻结不改，两者冲突时以本补充为准。

## 修改内容

第 4 节放行条件第 3 条改为：`/data2/FreeToken/run/production.active.json` 的 `approval_id` 为 `RESTORE481-MORNING-20261011-09` **或** `RESTORE481-MORNING-20261011-10`，`commit` 为 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`，且 `/health` 返回 `status=ok`、`maintenance=serving`。

## 修改原因

Gemini 今晚可能开一个 GPU 窗口（`plan/GEMINI_OOM_HYBRID_20261011.md`）。窗口结束后，生产恢复时的审批号是 -10。两个审批号对应的是同一个发布版 481d3a7，启动参数也相同。

## 避让规则

- Gemini 的窗口会在你的测量结束之后才开始。具体是：你在协调日志写出"D11-P0 测量完成"或"D11-P0 今日不测"；或者到 21:00 时，服务器上既没有 `stall_probe.py` 进程，`runs/dev_d11_p0_20261011/` 下最近 10 分钟也没有文件更新。
- 你测完后，请务必在协调日志写一行"D11-P0 测量完成"；决定今天不测时，写"D11-P0 今日不测"。
- 如果放行条件检查时发现 481 已停（Gemini 窗口进行中），本次不跑，记录原因，等 481 恢复后再按第 4 节重新检查。
