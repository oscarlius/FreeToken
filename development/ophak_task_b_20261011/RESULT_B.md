# op-hak 任务 B 结果报告（窗口与 W5，2026-10-12 凌晨）

- 指令：`plan/OPHAK_TASK_B_CUT_POLICY_20261011.md`（SHA256 `64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186`）
- 预登记：`PREREG_TASK_B_v2.json`（SHA256 `8df5ee4901795d287bed22cfaadbaef3515c89f530c4f9df26a5798489f9152d`）
- 放行：协调日志第 2412 行，主会话（freetoken-06），01:25:08
- 就绪：`CPU_READINESS_B.md`（SHA256 前 12 位 `a0569495ab60`），协调日志 01:24:09
- 执行者：op-hak
- 窗口：`--campaign b`，运行目录 `/data2/FreeToken/runs/dev_ophak_task_b_20261011/window_run/`（原始记录在 `window/<服务>/`）

## 0. 结论摘要

- **窗口终态 `complete`**：五个服务 R0、C_A1、C_B1、C_B2、C_A2 各 21 条请求全部完成；无死亡；清场全部成功；无 `CLEANUP_BLOCKED.md`。
- **判定（机械计算，`analyze_task_b.py`，`analysis.json` SHA256 前 16 位 `4c6ad0fdbf09ae97`）**：T16-lite 成立；G1 成立；G2 changed 成立；G2 unchanged 成立；G3 成立；G5 成立（阈值臂无 OOM、无 worker 退出）。
- **W5 已完成**（用 restore13 恢复）：冒烟 passed；观察器截止 `2026-10-12T09:00:00+08:00`，已在 09:00 之前完成。生产现为 release-e2（481d3a7），审批 `RESTORE481-MORNING-20261011-13`。
- 本报告不改生产配置。是否把阈值参数用到生产，由用户另行决定（指令 §6）。

## 1. 时间线（服务器时间，+08:00）

| 时刻 | 步骤 | 结果 |
|---|---|---|
| 01:25:08 | 放行（协调日志 2412） | 主会话写“任务 B 放行” |
| 01:26:55 | W0 `w0-check --campaign b` | 全部 PASS（`W0_CHECK_B.json`，SHA256 前 16 位 `7b84fae86ca50119`） |
| 01:28:24 | W1 清场记录 `w1_clearing_b.py` | 候选 0；GPU 上只有生产一个进程；CPU 超 50% 的进程 0；未停任何东西（`CLEARED_B.json`，前 16 位 `63586ea209a740d6`） |
| 01:28:33–34 | W2 停 -12 观察器 | 进程组 3359742 身份核对全部一致；只发 SIGTERM；0.5 秒内退出；未用 KILL；样本数 162 → 162（`W2_OBSERVER_STOP_B.json`，前 16 位 `cb23119e08c285da`） |
| 01:28:41–01:29:05 | W3 停 481（-12），restore12 冻结控制器 | 返回码 0；`stopped.json` 的 `resources_released` true、`errors` 空、`supervisor_exit` true（前 16 位 `0cde6787a13ed171`）；`production.active.json` 与 `gpu.lock` 不存在；GPU 计算进程为空，显存 4 MiB；8095、8096、8123 无监听 |
| 01:29:25 | 窗口开始 | 窗口运行器 `taskset -c 0,2`，服务进程 argv 绑核 1,3–47 |
| 01:37 前后 | R0 ready 并完成 | 健康接口加载约 500 MB/s，未触发 600 秒 ready 超时 |
| 02:05:28 | 窗口结束 | `terminal: complete`（`window/window_summary.json`，前 16 位 `ef80386433a3480e`） |
| 02:06:18 | W5 第一步：启动 | `start_approved_release.py`，状态 `started_waiting_serving`，审批 -13，监督进程 pid 3908935，服务 pid 3908998，GPU 锁归属 `production:release:RESTORE481-MORNING-20261011-13` |
| 02:11:16 | W5 第二步：等待 serving 并冒烟 | `classification: passed`，`exit_code: 0`，提示长度 [512, 8257]，每条输出 128 token（`W5_wait_B.log`，前 16 位 `fdf9f8193cf5d7ea`） |
| 02:11:33 | W5 第三步：起观察器 | `post_night_observer.py` pid 3923896，`observe_overnight.py` pid 3923898（即 `observer_pid`）；`until` `2026-10-12T09:00:00+08:00`（`start.json`，前 16 位 `d2069091b32c45f2`） |

W5 之后的核对：健康接口 `status: ok`，serving；`production.active.json` 为 `RESTORE481-MORNING-20261011-13`，mode release，commit `481d3a707481`；GPU 锁 owner 为 `production:release:RESTORE481-MORNING-20261011-13`。

## 2. 构建门与参数门（每个服务，`build_gate.json`、`param_gate.json`）

| 服务 | 臂 | 构建门：导入根目录 | 构建门 | 参数门：期望 / 实际 | 参数门 |
|---|---|---|---|---|---|
| R0 | on | `/data2/FreeToken/wt/release-e2` | ok | 字段缺省 / 缺省 | ok |
| C_A1 | on | `/data2/FreeToken/wt/m1-cutmin-20261011` | ok | 0 / 0 | ok |
| C_B1 | thresh | 同上 | ok | 32768 / 32768 | ok |
| C_B2 | thresh | 同上 | ok | 32768 / 32768 | ok |
| C_A2 | on | 同上 | ok | 0 / 0 | ok |

## 3. 逐服务结果（`window/window_summary.json`，各服务 `summary.json`）

| 服务 | 构建 | 臂 | 状态 | 完成请求 | 死亡 | 清场 | 显存 ready（MiB） | 请求前后显存 min–max（MiB，各 42 个采样） |
|---|---|---|---|---|---|---|---|---|
| R0 | release | on | complete | 21 | 无 | ok | 21544 | 21544–23720 |
| C_A1 | candidate | on | complete | 21 | 无 | ok | 21544 | 21544–23720 |
| C_B1 | candidate | thresh | complete | 21 | 无 | ok | 21544 | 21544–23720 |
| C_B2 | candidate | thresh | complete | 21 | 无 | ok | 21544 | 21544–23720 |
| C_A2 | candidate | on | complete | 21 | 无 | ok | 21544 | 21544–23720 |

`deaths: []`，`terminal: complete`。两个 B 臂服务的请求全部按计划完成，没有 OOM，没有 worker 退出标记。

## 4. 判定（`analysis.json`，`analyze_task_b.py`，输入哈希与 INPUTS.json 一致）

- **T16-lite（默认关闭等价）**：成立。R0 与 C_A1 的 20 轮（seed_real 0–7，T2 0–11）切段、cached、输出全文逐字相同；不符 0，缺 0。
- **G1（切段与 cached）**：成立。开臂服务（C_A1、C_A2）按 on_segments、阈值臂服务（C_B1、C_B2）按 thresh_segments，共 80 项，不符 0，缺 0。
- **G2 changed**：成立。14 轮（class = changed），Δ = 开臂两服务均值 − 阈值臂两服务均值，中位数 **2.6885 s**，最小 **2.6381 s**；判据为中位数 ∈ [2.3, 3.0] 且每轮 ≥ 1.8。预登记预测约 2.78 s。
- **G2 unchanged**：成立。T2 第 2、3、9、11 轮，中位数 **0.0118 s**（判据 |中位数| ≤ 0.3）。
- **冷轮（只报告，不进判读）**：seed_real/00 Δ = −0.5259 s；T2/00 Δ = 2.7183 s。
- **漂移**：0 次（同臂两服务同轮首 token 相差超过 10% 的事件数为 0），G2 未降级。
- **G3（同臂输出逐字相同）**：成立。(C_A1, C_A2) 与 (C_B1, C_B2) 的 40 对输出，不同 0。
- **G5（阈值臂无 OOM）**：成立。C_B1、C_B2 均 complete，无 OOM，无 worker 退出。

## 5. 逐轮首 token（秒，`requests.jsonl` 的 `ttft_s`，表中为原始值，四位小数）

| 轮次 | R0 | C_A1 | C_B1 | C_B2 | C_A2 |
|---|---|---|---|---|---|
| warm/00（不计判定） | 15.6351 | 16.0826 | 3.8247 | 3.9317 | 3.9279 |
| seed_real/00（冷，report） | 18.3434 | 17.2848 | 18.3681 | 17.2456 | 17.2771 |
| seed_real/01 | 5.7898 | 5.7041 | 2.9973 | 3.0027 | 5.7012 |
| seed_real/02 | 5.7559 | 5.6962 | 3.0059 | 3.0056 | 5.6573 |
| seed_real/03 | 5.7522 | 5.7194 | 2.9985 | 3.0125 | 5.6846 |
| seed_real/04 | 5.7603 | 5.7530 | 2.9992 | 3.0237 | 5.6803 |
| seed_real/05 | 5.7405 | 5.7481 | 3.0073 | 3.0293 | 5.6744 |
| seed_real/06 | 5.7998 | 5.7132 | 3.0082 | 3.0311 | 5.7043 |
| seed_real/07 | 5.7796 | 5.7117 | 3.0243 | 3.1010 | 5.6900 |
| T2/00（冷，changed，report） | 5.5555 | 5.6166 | 2.8549 | 2.8560 | 5.5309 |
| T2/01 | 5.4471 | 5.4817 | 2.7703 | 2.7713 | 5.4244 |
| T2/02（unchanged） | 2.7887 | 2.7614 | 2.7712 | 2.7699 | 2.7678 |
| T2/03（unchanged） | 2.7881 | 2.7724 | 2.7707 | 2.7606 | 2.7727 |
| T2/04 | 5.4526 | 5.4317 | 2.7717 | 2.7709 | 5.4286 |
| T2/05 | 5.4555 | 5.4356 | 2.7816 | 2.7723 | 5.4344 |
| T2/06 | 5.4979 | 5.5723 | 2.8010 | 2.7977 | 5.4677 |
| T2/07 | 5.4751 | 5.5138 | 2.8017 | 2.7915 | 5.4554 |
| T2/08 | 5.4815 | 5.5222 | 2.7977 | 2.8035 | 5.4627 |
| T2/09（unchanged） | 2.8107 | 2.8324 | 2.7978 | 2.7968 | 2.7954 |
| T2/10 | 5.4780 | 5.5088 | 2.8001 | 2.7984 | 5.4531 |
| T2/11（unchanged） | 2.8125 | 2.8346 | 2.7993 | 2.8001 | 2.7985 |

## 6. 观察（不进判定，照实记录）

1. **warm/00 首 token**：R0 与 C_A1 约 15.6–16.1 秒，C_B1、C_B2、C_A2 约 3.8–3.9 秒。warm/00 不在判定之内；R0 与 C_A1 是窗口里最先启动的两个服务，原因未核实。
2. **显存**：每个服务 ready 时 21544 MiB；请求前后整卡显存最高 23720 MiB，接近单卡 24 GB 规格。没有出现 OOM。
3. **ready 超时**：未触发。R0 的加载速度约 500 MB/s，ready 时间远低于 600 秒。
4. **W5 产生的文件**：`restore13/EXECUTION_TIME_PREFLIGHT.json` 在 W5 第一步由 `start_approved_release.py` 创建（恢复包设计如此，不是构建时的文件）。

## 7. 偏差

- 窗口与 W0–W5 的步骤均按指令与主会话的更正顺序执行，没有偏差。
- 没有需要停止的候选；没有死亡；没有清场阻塞；没有恢复失败。

## 8. 代码、测试与演练

- 候选提交 `9db0ee776c25afa8d2719ab700b2de7ccc606142`（分支 `m1/cut-min-tokens`，只在本地，未 push）。diff：6 个文件，+151 / −2。
- 测试基线（提交说明）：`tests/scheduler` 在 481d3a7 为 137 passed / 6 failed；在 9db0ee77 为 145 passed / 6 failed，失败项相同（既有）。
- 窗口所用运行器 `task_b_runner.py`，SHA256 前 16 位 `ce0da915b6b54154`（与定稿一致）。单测 33 项通过。
- 演练：8/8 通过（`REHEARSAL_B.json`，前 16 位 `40d33b693b8a187f`）。演练是桩服务按预登记复现，只核对路径与算术，不是证据。

## 9. 证据索引（服务器，SHA256 前 16 位）

| 文件 | 前 16 位 |
|---|---|
| `window_run/analysis.json` | `4c6ad0fdbf09ae97` |
| `window_run/window/window_summary.json` | `ef80386433a3480e` |
| `W0_CHECK_B.json` | `7b84fae86ca50119` |
| `CLEARED_B.json` | `63586ea209a740d6` |
| `W2_OBSERVER_STOP_B.json` | `cb23119e08c285da` |
| `W3_stop_B.log` | `93ff7811a209e2a8` |
| `runs/…/RESTORE481-MORNING-20261011-12/stopped.json` | `0cde6787a13ed171` |
| `W5_start_B.log` | `9d04dcdb4a9b44a5` |
| `W5_wait_B.log` | `fdf9f8193cf5d7ea` |
| `runs/…/RESTORE481-MORNING-20261011-13/overnight_observation/start.json` | `d2069091b32c45f2` |

原始记录：`window_run/window/<服务>/requests.jsonl`（每条请求的 TTFT、切段、cached、显存）、`outputs.json`、`summary.json`、`build_gate.json`、`param_gate.json`、`memory_ready.json`。

## 10. 主会话需要知悉的事项

1. G2 changed 的中位数 2.6885 s 比预登记的预测 2.78 s 低约 0.09 s，仍在判据区间内；判定由 `analyze_task_b.py` 机械给出，没有人工修改。
2. 窗口里 R0 与 C_A1 的 warm/00 偏慢，不在判定之内，原因未核实。
3. 请求期间显存最高 23720 MiB，未 OOM。阈值参数是否进入生产，由用户另定。
