# 补充 2：D11-P0 放行条件第 3 条再放宽（2026-10-11 晚，主会话）

适用于 `plan/CODEX_D11_P0_STALL_BASELINE_20261011.md`，以及补充 1（`…_ADDENDUM1.md`，a3cc96ef…）。

## 改动

第 4 节放行条件第 3 条改为：

- `/data2/FreeToken/run/production.active.json` 的 `approval_id` 为以下三者之一：
  - `RESTORE481-MORNING-20261011-09`
  - `RESTORE481-MORNING-20261011-10`
  - `RESTORE481-MORNING-20261011-11`
- `commit` 为 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`；
- `/health` 返回 `status=ok`、`maintenance=serving`。

## 原因

- Gemini 今晚还有一个 D09 窗口（`plan/GEMINI_D09_ENABLE_20261011.md`），结束后生产以 -11 恢复。三个审批号对应同一个发布版 481d3a7，启动参数也相同。
- Gemini 开窗前会避让你：只要服务器上有 `stall_probe.py` 进程，或 `SRV/runs/dev_d11_p0_20261011/` 最近 10 分钟有更新，它就会等你测完（最多 45 分钟）。
- 你开始测量前，请先确认生产在服务，并且没有 Gemini 窗口在进行：`/data2/_shared/gpu.lock` 的 owner 是生产，且 `SRV/development/gemini_d09_enable_20261011/` 下没有正在运行的 `runner.py` 或 `b_runner.py` 进程。

## 不变

其他条款都不变。测完后，在协调日志写"D11-P0 测量完成"；决定今天不测，则写"D11-P0 今日不测"。
