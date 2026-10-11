# op-hak 任务 A2：P1 就绪补充 1（/health 改为只记录）

- 依据：freetoken-06 的放行与答复（协调日志 2348–2351 行）。答复 2 选择方案 (b)：`/health` 只记录、不作判据；判定 worker 退出只看 serve.log 标记（请求进行中每 5 秒扫描，请求结束后复扫）。
- 指令：`plan/OPHAK_TASK_A2_T2_ONLY_20261011.md`（SHA256 `84fe10fc75542a26…`，不变）。

## 1. 改动（只限 /health 判定路径）

- `WorkerWatch.check_health()` 不再返回判定，只记录：连续失败次数 `health_failures`、本请求内的最大连续失败次数 `health_failures_max`、最后一次结果 `health_last`（`"ok"`、`"status:<值>"` 或 `"error:<异常类名>"`）。
- `WorkerWatch.poll()` 先扫 serve.log 标记，命中即返回；未命中才查一次 `/health` 并记录。因此命中标记的那次轮询不查 `/health`，中止行的 `health_last` 为空。
- `post_chat_watched` 把 `health_failures_max` 与 `health_last` 放进请求记录（`run_request` 的记录合并了这些字段）。
- 删除常量 `HEALTH_FAIL_LIMIT`（已无引用）。判定逻辑未变：OOM 文本与 worker 标记、每 5 秒扫描、请求结束后复扫。
- 判读脚本（`analyze_task_a.py`、`analyze_task_a2.py`）不读取这两个字段，已核对。

## 2. 文件与 SHA256（前 16 位，服务器与本地一致）

| 文件 | SHA256（前 16 位） |
|---|---|
| `task_a_runner.py` | `112917c56034acd6` |
| `test_task_a_runner.py` | `95b81c75e24157f3` |

## 3. 单元测试

- 服务器 `venv-eval` pytest（`-p no:cacheprovider`）：**34 passed**（原 32 项；替换 1 项，新增 2 项）。
- 替换：`test_two_consecutive_health_failures_trip_and_a_healthy_reply_resets` → `test_health_failures_are_recorded_and_never_trip`（连续失败不判定，计数与状态写入，成功则清零连续计数）。
- 新增：`test_marker_still_trips_while_health_keeps_failing`（健康检查持续失败时，标记仍判定）；`test_watch_outcome_carries_health_counters`（请求记录带上计数）。
- 中途退出测试注入拒绝连接的健康检查，避免单测触发真实网络。

## 4. 复核（改后代码）

**演练复核**（`recheck_health_record_only`，缩放 0.05，只占核心 0 与 2）：
- R_a_worker_exit：B1_off 在 T2/05 标 worker_exit，复扫路径，时延 0.001 s；其它三个服务各完成 13 条（ok）；终态 complete。
- R_a_hang：B1_off 在 T2/05 标 worker_exit，在途识别（watch_polls=1），客户端在 5.0 s 主动断开，时延 4.82 s；其它三个服务各完成 13 条（ok）；终态 complete。

**真实 HTTP 健康检查**（此前只有注入的假函数，本次在真实桩服务上验证）：
- 存活桩 `127.0.0.1:18460`：`default_health_get` 返回 `status: ok`；`poll()` 不判定，`health_last = "ok"`，连续失败 0。
- 关闭的端口 `127.0.0.1:18461`：`poll()` 不判定，`health_last = "error:ConnectError"`，连续失败 1，最大值 1。
- 临时桩进程已停止。

## 5. 说明

- `REHEARSAL_A2.json`（四项演练，`sources` 里的运行器为 `c24cb9681b24…`）是改动前生成的，本次没有重跑全部演练。改动只影响 /health 的记录，不影响判定路径；两项挂起/复扫演练已用改后代码复核（第 4 节）。
- 本补充不改变 `CPU_READINESS_A2.md` 的其它内容。原文第 2 节和第 8.1 节关于 /health 判据的描述，以本文件为准。
- W0 在本文件写完后执行，W0 通过后 45 分钟内必须开窗（`W0_MAX_AGE_S` = 2700 秒）。
