# op-hak 任务 A2：P1 就绪记录（CPU 阶段，2026-10-11）

- 指令：`plan/OPHAK_TASK_A2_T2_ONLY_20261011.md`（SHA256 `84fe10fc75542a26…`，本地与服务器一致）
- 预登记：`development/anchor_cut_accounting_20261011/PREREG_TASK_A.json`（SHA256 `0e1708bf033f26ec…`，两侧一致，与 REHEARSAL_A2.json 记录的一致）
- 执行者：op-hak
- 结论：**P1（CPU 阶段）完成。未开窗，未停 481，未在 GPU 上运行任何服务。等待主会话在协调日志写"任务 A2 放行"。**

## 1. 做了什么，没做什么

| 项 | 做了 | 没做 |
|---|---|---|
| 工装改动（指令 §3 的三项） | T2-only 计划；请求进行中的 worker 退出实时识别；每请求前后及就绪时的显存采样；单测 32 项通过（A2 新增 12 项） | 没有在 GPU 上运行真实服务（P2 才做） |
| 演练 | 四项演练全部完成，`REHEARSAL_A2.json` 全部检查通过（正向 + 三项反向） | 演练用桩服务，只证明工装路径，不是证据 |
| restore12 预检 | pytest 7 passed；门链通过；`-12` 的 run_dir 不存在；预检前后文件清单不变 | 没有执行恢复（只在 W5 执行） |
| 就绪 | 本文件；协调日志"任务 A2 P1 就绪"一行 | — |

资源：演练进程绑定在 CPU 核心 0 与 2 上，只用端口 18400–18430，没碰 8095。nvidia-smi 只做读数采样。

## 2. 工装改动（指令 §3）

1. **T2-only**：`CAMPAIGNS["a2"]["trajectories"] == ("T2",)`。计划为 warm/00 加 T2/00–T2/11，每服务 13 条，ABBA 顺序，不含 seed_real。
2. **worker 退出即时识别**：
   - 请求进行中：每 5 秒（`WATCH_POLL_S`）检查一次 serve.log 的新增字节，并查一次 `/health`（超时 3 秒）。serve.log 命中 OOM 文本（`out of memory`，不区分大小写）或 worker 标记（`backend worker \S+ exited` / `backend worker is gone`）即判定；`/health` 连续两次失败或 status 不为 ok 判 worker_exit。命中后主动断开客户端，服务进程由清场结束。
   - 请求结束后复扫：客户端先看到连接错误、而标记尚未被轮询到的情况，也记为 worker_exit（消除竞态）。
   - 窗口规则：OOM 或 worker_exit 只停该服务，窗口继续；其它非 ok 状态停窗口，之后执行 W5。
   - 匹配样本：`fixtures/window01_b1_off_markers.log` 逐字取自 window01 B1_off serve.log 第 87–89 行。
3. **显存采样**：每条请求发送前、返回后各一次（`nvidia-smi memory.used`），服务就绪时一次（`memory_ready.json`）。只报告，不设判据。

## 3. 文件与 SHA256（前 16 位，服务器与本地一致）

| 文件 | SHA256（前 16 位） | 作用 |
|---|---|---|
| `task_a_runner.py` | `c24cb9681b244ef7` | 运行器（A2 三项改动） |
| `stub_server.py` | `55b4be5de181ddc3` | 桩服务；新增 `--worker-exit-hold-s`（挂起不断开） |
| `analyze_task_a.py` | `2bedfb5db2f772a1` | 任务 A 判读（未改） |
| `analyze_task_a2.py` | `be3fb71f123fc1c9` | A2 机械判读（T2-only） |
| `test_task_a_runner.py` | `b5a29d246b81c032` | 单测 32 项 |
| `run_rehearsals_a2.sh` | `e495891dd6599d5a` | 四项演练的启动脚本 |
| `make_rehearsal_a2_report.py` | `8cc59d0389d65551` | 演练核对，写 REHEARSAL_A2.json |
| `INPUTS.json` | `7931e9a9854526d8` | 输入冻结（未改） |
| `REHEARSAL_A2.json` | `143e1d4d4e46a3d5` | 演练核对结果（0444） |

## 4. 单元测试与变异检查

- `venv-eval` 的 pytest（`-p no:cacheprovider`）：**32 passed**。A2 新增 12 项，覆盖：T2-only 计划与 warm/00；a2 参数与放行/就绪行格式；window01 三行原文匹配；普通服务日志不误判；`/health` 连续两次失败触发、成功则复位；请求进行中 worker 退出 10 秒内识别并断开；标记先于连接断开的竞态；无标记的断开仍为 request_error；请求前后显存采样；就绪显存写入；worker 退出只停该服务；cached 错配被逐轮核对标出。
- 变异检查：A2 工装改动后，在临时副本上植入三处缺陷，各被 1 项测试捕获。
- 桩服务的挂起开关没有单测，由 R_a_hang 演练覆盖（真实 HTTP 链路）。

## 5. 演练结果（REHEARSAL_A2.json，`all_pass: true`）

| 演练 | 配置 | 结果 | 关键证据 |
|---|---|---|---|
| **R_positive** 正向 | 缩放 1.0，完整 T2 计划，端口 18400 | 通过（36 项） | 四个服务各完成 13 条（全部 ok）。G2 中位数 2.7804 s（区间 2.3–3.0），每个变化轮 Δ 最小 2.7767 s。阴性对照 \|中位数\| 0.0001 s。同臂漂移超限 0 轮。冷轮 T2/00 Δ 2.783 s（[2.0, 3.0]）。切段与 cached 无不符。S0 无失败。同臂输出逐字相同 |
| **R_a_worker_exit** 反向 (a) | 缩放 0.05，B1_off 在 T2/05 退出，端口 18410 | 通过（39 项） | 窗口继续。B1_off 完成 6 条后标 worker_exit，T2/05 之后没有请求。其它三个服务各完成 13 条。识别路径：请求结束后复扫（watch_polls=0），时延 0.0008 s。Δ 缺失的轮次 = T2/05、06、07、08、10（中止后的变化轮） |
| **R_a_hang** 反向 (a′) | 同上，但标记后挂起 30 秒不断开，端口 18430 | 通过（41 项） | 识别路径：请求进行中的实时监视（watch_polls=1）。客户端在约 5.0 s 主动断开，远短于 30 s 挂起。时延 4.82 s（<10 s） |
| **R_b_wrong_cached** 反向 (b) | 缩放 0.05，A1_on 的 T2/02 返回 cached=0，端口 18420 | 通过（35 项） | 复用不符只标在 A1_on 的 T2/02：usage 与首条 Prefill 行都为 0，预登记为 12736。切段无不符 |

说明：
- 缩放演练的 G2 绝对判读显示"不成立"（中位数约 0.14 s，即 0.05 × 2.78）。这是缩放造成的，不是判读失败。报告按缩放后的区间核对。
- 显存：每条请求前后及就绪时都有读数，全部为 22454 MiB，演练期间增量为 0。读数来自生产 481 占用的 GPU，与桩服务无关。这只说明采样路径可读，不说明显存行为。
- 演练过程中修正过一处：报告脚本第一次 dry-run 把中止行的 S0 误报为失败（中止行没有 usage，S0 无从核对）。已改为只核对 ok 行（与 analyze_task_a2 一致），并增加"中止行无 usage"的检查。修正后全部通过。
- 挂起开关加入后，四项演练整体重跑了一遍。修改前的一轮保留在服务器 `rehearsal_attempt1_before_hang_mode/`，不作为证据。

## 6. restore12 预检（A2 §5，W5 前置）

- `pytest test_cpu_orchestration.py`：**7 passed**（`CUDA_VISIBLE_DEVICES` 为空，`taskset -c 0,2`，`-B -p no:cacheprovider`）。
- 门链：`GATE_CHAIN_PASS RESTORE481-MORNING-20261011-12 2026-10-12T09:00:00+08:00`（rc 0）。
- `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-12` 不存在。
- 预检前后 restore12 的文件清单（16 个文件）摘要一致，没有生成缓存目录。
- 恢复包的构建与门链沿用 `CPU_READINESS.md` §4，本次没有改动。开窗前会在用前再跑一次。

## 7. 生产与观察器（只读检查，22:07）

- 481 仍为 -11：`172.16.108.9:8095/health` 返回 200，`status: ok`，`maintenance: serving`，`backend_epoch: 0`，`restart_attempts: 0`，`uptime_s: 2247`。
- `production.active.json`：`approval_id` RESTORE481-MORNING-20261011-11，commit `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`，worktree `/data2/FreeToken/wt/release-e2`。
- 观察器 PID 3136499 仍在运行（`observe_overnight.py`，`--until 2026-10-12T09:00:00+08:00`）。
- `/data2/_shared/gpu.lock` 存在（生产持有）。

## 8. 风险与需要主会话确认的事项

1. **`/health` 判据未在真实服务上验证**。指令规定每 5 秒查一次、超时 3 秒、连续两次失败即判 worker_exit。冷 87K 预填约 18 秒。若期间 `/health` 慢于 3 秒或返回非 ok，会误判并中止该服务。误判后日志里没有标记行，可据此排查，但窗口的记录里 `watch_trip` 只会写 worker_exit，分不出是日志标记还是 `/health` 触发的。
   - 可选的调整（需主会话决定，我没有改）：(a) 保持现状；(b) 只用日志标记判退出，`/health` 只记录不触发；(c) 把失败次数阈值改为 3。
2. **在途识别的时延上限**：最坏约 8 秒（5 秒轮询加上一轮 `/health` 最长 3 秒超时），低于 10 秒的要求。
3. **中止行的 `ttft_s` 为空**（在途路径下客户端被断开）。只影响中止行；判读只用 ok 行，不影响结论。
4. **显存根因无法从日志核实**：serve.log 的 Prefill 行没有 GPU 字段，只有启动时的空闲显存行。窗口只能报告显存轨迹，不能给出原因。
5. **window02 运行目录指令没有给出**。我计划用 `/data2/FreeToken/runs/dev_ophak_task_a2_20261011/window02`（与演练目录并列）。按指令"指令没写到的情况，停下，发消息给我"，请主会话确认后再开窗。
6. **W5 恢复为 -12** 会使原 D11-P0 指令的预检失效。按主会话的裁定，由主会话处理。
7. **45 分钟时限与 6 分钟保留**：已按指令实现（`limit_s` 2700，`reserve_s` 360）。
8. **演练结果不是证据**：Δ = 2.78 s 只证明算术正确。预测是否成立只能由 P2 的真实窗口回答。

## 9. 放行后的执行顺序（指令 §5–§8）

- W0：`w0-check --campaign a2`（批准号 -11）。
- W1：清场记录。
- W2：停观察器 PID 3136499（先核对进程身份，再发 TERM）。
- W3：用 restore11 的 `stop_approved_restore.py` 停 -11（rc 0；`stopped.json` 写入 -11 目录；`production.active.json` 移除；`gpu.lock` 释放）。
- W4：`window --campaign a2`（detached，run_dir 为 window02）。
- W5：用 restore12 恢复（`start_approved_release.py` → `wait_release_and_smoke.py`（`CUDA_VISIBLE_DEVICES` 为空）→ `post_night_observer.py`，`setsid -f`），先重跑 §6 的预检。
- RESULT_A2.md（0444），含内存轨迹表，然后在协调日志写"任务 A2 窗口结束，等主会话复核"。
