# E2-R046 batch73 G3-on timeout diagnosis — 2026-10-07

## Finding

The G3-on server accepted the streaming HTTP request but never admitted it to the
scheduler. This is caused by the opt-in `FT_DEV_PAUSE_ENDPOINT=1` scheduler
loop, not by route collection or a default pause interval.

`Scheduler._dev_normal_loop()` calls `_receive_dev_messages(blocking)`. That
method appends every non-pause message, including `UserMsg`, to
`_dev_deferred_msgs`. The only release call is in `_start_dev_pause()`, which
runs only when `_dev_pending_pauses` is non-empty. A normal chat request with
no `/dev/pause` request therefore remains deferred indefinitely.

## Batch73 evidence

- `g3_on/SERVE_CMD.txt` enabled `FT_DEV_PAUSE_ENDPOINT=1` and
  `FT_DEV_ROUTE_TRACE`; G3-off enabled neither development variable.
- `g3_on/serve.log` records readiness at `23:59:31`, the stream POST `200` at
  `23:59:34`, then `Scheduler is idle`; it contains no prefill/route record.
- The caller timed out at `00:29:34`; the preserved failure is
  `TimeoutError('timed out')`. This is before any route trace or cold result.
- Candidate source: `scheduler.py:341-352` selects the dev loop;
  `scheduler.py:1022-1028` defers non-pause messages; `scheduler.py:1078-1084`
  releases them only after a pause.

## CPU confirmation

`/data2/FreeToken/runs/dev_D07/r046_batch73_pause_scheduler_cpu_20261007_004640/result.json`
SHA-256 `70717167a82e6378eaef2475d42762896780e9c977cc5e19280134d87e930f86`
executed the actual candidate `Scheduler._dev_normal_loop` with a synthetic
ordinary message and no pending pause. It confirmed the message is deferred,
not processed, while normal scheduling continues. `CUDA_VISIBLE_DEVICES=''`;
no socket, model service, or GPU was used.

## Scope consequence

This requires a candidate-source repair and CPU regression proving ordinary
messages are released when no pause is pending while pause windows still defer
them. It cannot be remedied by replaying R046 or changing client timeouts.
No candidate or frozen source was changed here.

2026-10-07 01:12：修复已形成独立本地开发提交 effb9969706922ddad9e59b96377e46469ebe97f，定版候选保持 0aa。旧 draft patch 的 hunk 格式错误已由实际 Git apply 检出；新 draft_v2 从真实 diff 生成，并经六次真实 patch 应用后的候选方法 CPU 回归通过（报告4adbbbd53773eb91064788a4f9411799e3ae331c4ab3e866189b2cf42b774c6e）。该提交尚未激活或开展 GPU 验证，正式候选/工装路径需用户裁定。
