# 任务 A 窗口结果报告（op-hak，2026-10-11 夜）

> 只写数据与按 §6 的机械结论。窗口未完成，G2–G4 因 B 臂与 A2 缺失而无数据。

## 0. 结论摘要

- 窗口终态：`request_error`（工装记录）。A1_on 完整（21/21）。B1_off 在热轮 `seed_real/02` 发生服务端 OOM，客户端按工装记为 `request_error`（ReadTimeout 600 s）。A2_on、B2_off 未运行。
- G5 字面（冷 87K 单段 OOM）：**未触发**。B1_off 的 `seed_real/00`（冷 87,100，单段）预填通过。
- 另记一个事件（不在 G5 字面范围内）：B1_off 在热轮 `seed_real/02` 发生 OOM，见第 4 节。
- 481 已以 `RESTORE481-MORNING-20261011-11` 恢复（服务就绪 21:29:45，冒烟通过，观察器已起，见第 5 节）。
- 当前 /health：`{"status":"ok","model":"Qwen3.8-Flash-Next-NVFP4","instance_id":"98c90705-1a36-4cb8-a868-e77720ac2729","uptime_s":138,"version":"0.1.3","maintenance":"serving","backend_epoch":0,"restart_attempts":0,"restart_waiters":0}`

## 1. 每一步的终态与时刻

| 步骤 | 终态 | 时刻（服务器时间） | 依据 |
|---|---|---|---|
| W0 | 通过 | 2026-10-11T20:59:06+08:00 | W0_CHECK.json SHA `d8a8f195ee7d` |
| W1 清场 | 候选 0 个，停止 0 个 | 2026-10-11T20:59:53+08:00 | CLEARED.json SHA `bc3fc33ed006` |
| W2 停 -10 观察器 | stopped | 2026-10-11T21:00:37+08:00 | SIGTERM 进程组 2635718，未用 KILL；samples 155 → 155 |
| W3 停 481 | 退出码 0 | 2026-10-11T21:01:30+08:00 | stopped.json；production.active.json 已删；gpu.lock 已释放；GPU 无计算进程 |
| W4 窗口开始 | — | 2026-10-11T21:01:58+08:00 | window01 |
| W4 窗口结束 | `request_error` | 2026-10-11T21:24:14+08:00 | window_summary.json |

## 2. 逐服务逐轮记录

### A1_on（锚点切段开，= 生产配置，仅 host/port 不同）

状态：complete，完成 21/21。

| 轮次 | 状态 | prompt_tokens | cached（usage） | 切段（new_token, cached） | 切段与预登记 | cached 与预登记 | ttft_s | total_s | 输出 SHA 前 12 |
|---|---|---|---|---|---|---|---|---|---|
| warm/00 | ok | 54 | 0 | (54, 0) | — | — | 17.39 | 17.7 | 846dea26060e |
| seed_real/00 | ok | 87100 | 0 | (22272, 0), (64828, 0) | 是 | 是 | 19.41 | 20.5 | 7e2942a0d086 |
| seed_real/01 | ok | 87328 | 87040 | (64, 87040), (224, 0) | 是 | 是 | 5.70 | 6.8 | cd6d9ffc7987 |
| seed_real/02 | ok | 87484 | 87296 | (64, 87296), (124, 0) | 是 | 是 | 5.67 | 6.9 | 5f16a2d3af46 |
| seed_real/03 | ok | 89295 | 87424 | (128, 87424), (1743, 0) | 是 | 是 | 5.68 | 6.7 | defbee16e00b |
| seed_real/04 | ok | 90697 | 89280 | (64, 89280), (1353, 0) | 是 | 是 | 5.68 | 6.8 | 140caf49160f |
| seed_real/05 | ok | 90940 | 90688 | (64, 90688), (188, 0) | 是 | 是 | 5.66 | 6.7 | 902b5d8237a6 |
| seed_real/06 | ok | 93269 | 90880 | (128, 90880), (2261, 0) | 是 | 是 | 5.75 | 6.8 | 20cd1c419061 |
| seed_real/07 | ok | 95352 | 93248 | (64, 93248), (2040, 0) | 是 | 是 | 5.77 | 6.8 | cd8d09946586 |
| T2/00 | ok | 12443 | 0 | (512, 0), (11931, 0) | 是 | 是 | 5.55 | 6.7 | 77b34ac2bc88 |
| T2/01 | ok | 12737 | 12416 | (64, 12416), (257, 0) | 是 | 是 | 5.43 | 6.6 | 4a39042cebcb |
| T2/02 | ok | 13067 | 12736 | (331, 12736) | 是 | 是 | 2.79 | 3.9 | 2ceb743a8e2b |
| T2/03 | ok | 13272 | 13056 | (216, 13056) | 是 | 是 | 2.78 | 3.9 | af5c486ee2df |
| T2/04 | ok | 13432 | 13248 | (64, 13248), (120, 0) | 是 | 是 | 5.44 | 6.7 | 8b1cbace5826 |
| T2/05 | ok | 14103 | 13376 | (64, 13376), (663, 0) | 是 | 是 | 5.44 | 6.5 | cadd3401475d |
| T2/06 | ok | 19000 | 14080 | (128, 14080), (4792, 0) | 是 | 是 | 5.48 | 6.7 | ecebd0560702 |
| T2/07 | ok | 20143 | 18944 | (128, 18944), (1071, 0) | 是 | 是 | 5.46 | 6.6 | cfe2c2934340 |
| T2/08 | ok | 21299 | 20096 | (128, 20096), (1075, 0) | 是 | 是 | 5.47 | 6.6 | 7ecce35309eb |
| T2/09 | ok | 21338 | 21248 | (90, 21248) | 是 | 是 | 2.80 | 3.8 | af9af9087805 |
| T2/10 | ok | 21596 | 21312 | (64, 21312), (220, 0) | 是 | 是 | 5.47 | 6.6 | e682d911f355 |
| T2/11 | ok | 21976 | 21568 | (408, 21568) | 是 | 是 | 2.81 | 3.9 | 7ba4bf84bbfc |

### B1_off（锚点切段关，`--no-prefill-anchor-cut`）

状态（工装）：request_error，完成 3/21，原因：timeout: ReadTimeout('timed out')。

| 轮次 | 状态 | prompt_tokens | cached（usage） | 切段（new_token, cached） | 切段与预登记 | cached 与预登记 | ttft_s | total_s | 输出 SHA 前 12 |
|---|---|---|---|---|---|---|---|---|---|
| warm/00 | ok | 54 | 0 | (54, 0) | — | — | 3.74 | 4.1 | 846dea26060e |
| seed_real/00 | ok | 87100 | 0 | (87100, 0) | 是 | 是 | 17.10 | 18.2 | e680c4a80aac |
| seed_real/01 | ok | 87328 | 87040 | (288, 87040) | 是 | 是 | 3.02 | 4.1 | d4f91cc9a0c4 |
| seed_real/02 | timeout | — | — | — | 无数据 | 无数据 | — | 600.1 | — |

### A2_on、B2_off

未运行（窗口在 B1_off 之后停止）。

## 3. 机械结论（analysis.json，按 §6）

- G1 切段不符（按服务，仅统计已完成的记录）：无
- cached 不符（按服务，仅统计已完成的记录）：无
- G2：无数据（中位数 无，缺失轮 14 个）
- G2 阴性对照：无数据
- G2 漂移：无数据（同臂两服务均未完成，无可比对的轮次）
- G3（同臂逐字相同）：无数据（A2、B2 未运行）
- G4（ON 对 OFF 输出）：无数据（B 臂不完整）
- G5 字面（冷 87K 单段）：关闭锚点切段后冷 87K 单段未 OOM（B1_off seed_real/00 状态 `ok`）

## 4. 事件：B1_off 热轮 seed_real/02 的服务端 OOM

- 服务端日志（`window01/window/B1_off/serve.log`）：
  - 21:13:42 API ready；21:13:47 warm 预填（54 token）；21:14:05 `seed_real/00` 预填（87,100 token，单段，cached 0）通过；21:14:11 `seed_real/01` 预填（288 token，cached 87,040）通过；
  - `seed_real/02` 开始后，服务端无预填行；21:14:37 在 `qsa_sparse_paged_attention` → `_qsa_sparse_paged_gqa_splitk_kernel` 的 Triton kernel 启动处报 `RuntimeError: Triton Error [CUDA]: out of memory`；
  - 21:14:37 后端 worker 退出，21:14:47 `Backend worker is gone and cannot be restarted; stopping the API server`。
- 客户端：服务端关闭时未发送错误包，`seed_real/02` 一直等到 600 s 读超时，因此工装记为 `request_error`。工装的分类没有识别出这次 OOM。这是工装的局限，不是服务正常。
- 与 G5 的关系：G5 字面针对冷 87K 单段（第 0 轮），该项通过。本事件发生在热轮，G5 没有对此给出预测；由主会话判定其含义。
- OOM 摘录（操作者按上述日志截取，前后 40 行）：`B1_oom_excerpt_operator.log`。

## 5. W5 恢复（restore11）

- 第一步 `start_approved_release.py`：rc=0；状态行 `{"status": "started_waiting_serving", "approval_id": "RESTORE481-MORNING-20261011-11", "run_dir": "/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11", "supervisor": {"pid": 3119020, "sta`
- 服务就绪（serving_ready.json）：2026-10-11T21:29:45+08:00，health 摘要：`{"status": "ok", "model": "Qwen3.8-Flash-Next-NVFP4", "instance_id": "98c90705-1a36-4cb8-a868-e77720ac2729", "uptime_s": 4, "version": "0.1.3", "maintenance": "serving", "backend_epoch": 0, "restart_a`
- 第二步 `wait_release_and_smoke.py`：`{"approval_id": "RESTORE481-MORNING-20261011-11", "exit_code": 0, "classification": "passed", "completed_at": 1791725416.8744369, "invocation": {"approval_id": "RESTORE481-MORNING-20261011-11", "argv": ["/data2/FreeToken/venv/bin/python", "`；rc=0
- 冒烟回执：exit_code=0，classification=passed；冒烟测试 `test_release_smoke` 内含与基准的比对（`compare_with_baseline`：sha256、usage、后端缓存行结构），pytest 结果 `1 passed`。
- 第三步观察器：start.json 已写出（until=2026-10-12T09:00:00+08:00，observer_pid=3136499）
- 现场 /health：`{"status":"ok","model":"Qwen3.8-Flash-Next-NVFP4","instance_id":"98c90705-1a36-4cb8-a868-e77720ac2729","uptime_s":138,"version":"0.1.3","maintenance":"serving","backend_epoch":0,"restart_attempts":0,"restart_waiters":0}`
- 清场记录：W1 没有停止任何东西，无需恢复。

## 6. 证据索引（SHA256 前 12 位）

- `/data2/FreeToken/development/ophak_task_a_20261011/W0_CHECK.json`：`d8a8f195ee7d`
- `/data2/FreeToken/development/ophak_task_a_20261011/CLEARED.json`：`bc3fc33ed006`
- `/data2/FreeToken/development/ophak_task_a_20261011/W2_OBSERVER_STOP.json`：`4b96106707b7`
- `/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01/window/window_summary.json`：`155a0dfbe4c7`
- `/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01/analysis.json`：`cafc815caeb5`
- `/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01/window/A1_on/requests.jsonl`：`966381b7a580`
- `/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01/window/B1_off/requests.jsonl`：`73e8664c0b60`
- `/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01/window/B1_off/serve.log`：`18bba9dbb7ab`
- `/data2/FreeToken/development/ophak_task_a_20261011/W5_start.log`：`96f9dc81b69a`
- `/data2/FreeToken/development/ophak_task_a_20261011/W5_wait.log`：`496cb0adab01`
- `/data2/FreeToken/development/ophak_task_a_20261011/REHEARSAL.json`：`e8af4f6ae3bd`
- `/data2/FreeToken/development/ophak_task_a_20261011/restore11/DEPLOYMENT_APPROVAL.json`：`c8fb07f3abcc`
- `/data2/FreeToken/development/ophak_task_a_20261011/restore11/ROOT_FINAL_REVIEW.json`：`01bc3861de23`
- `/data2/FreeToken/development/ophak_task_a_20261011/restore11/SOURCE_MANIFEST.json`：`ad41896091cd`

## 7. 偏差与待主会话判定的事项

1. B1_off 的工装分类为 `request_error`（ReadTimeout），经服务端日志确认为 OOM（热轮 seed_real/02）。窗口文件保留工装原始分类，本报告的 OOM 归类由操作者依据日志作出。
2. G5 字面（冷 87K 单段 OOM）未触发；OOM 发生在热轮。是否在 G5 名下记录，或另立事件，由主会话决定。
3. 窗口在 B1_off 之后停止，A2_on、B2_off 未运行。G2–G4 无数据，不做推断。
4. 未重跑、未补测，按主会话指示等待复核。

