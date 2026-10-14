# op-hak 任务 S：停顿测量——另一会话预填时，正在输出的会话卡多久（2026-10-11 夜，主会话 freetoken-06）

> 读者是执行者 op-hak。角色、红线、协调日志格式、"失败不重试"、"指令没写到就停下"等通用规则，沿用 `plan/OPHAK_TASK_A_ANCHOR_CUT_20261011.md` §0。本文件发出后冻结（0444），更正另发补充。用户已确认本任务（菜单第 2 项）。
>
> **预登记**：`development/anchor_cut_accounting_20261011/PREREG_TASK_S_v2.json`，SHA256 `76190ca79b370a248e14073d18d43732b199e0432c32f4fb7ed33cac9d493a5d`，下发前已封存。判读一律以它为准。v1（`e3eaf868…`）在下发前自检中被替代，原因写在 v2 的 `supersedes` 字段，替代前未见任何数据。

## 1. 要回答的问题

论文支柱一里唯一从没实测过的主张：**另一个请求预填期间，正在输出的会话完全停顿，停顿时长约等于那个请求的预填时长。**

依据：调度器总是先排预填（`scheduler/scheduler.py:1043-1046`）；被切成两段的请求，续段仍在预填队列里，两段之间不会插入别人的解码。所以预测"一段"的轮次停约 2.8 s，"两段"的轮次停约 5.4 s，L64（两段，64,000 token）停约 13.6 s。

## 2. 在哪测

**在生产 481 上测，不停服。** 审批号以 `SRV/run/production.active.json` 为准（写本文时为 -12），不写死。并发 2（A + B），全程约 6 分钟，不属于压力测试。生产 `--max-running-requests 2`，测量期间两个运行槽都被占用，局域网用户的请求会排队。

## 3. 测什么

### 3.1 会话 A（持续输出）

payload 固定为：

```json
{"model": "Qwen3.8-Flash-Next-NVFP4", "messages": [{"role": "user", "content": "从 1 开始，每行写一个整数，一直写下去。"}], "temperature": 0, "max_tokens": 16384, "ignore_eos": true, "stream": true, "stream_options": {"include_usage": true}}
```

- 不带 tools。**非空增量**的定义与任务 A2 工装相同：`reasoning_content` 或 `content` 非空；`tool_calls` 单独记录，不计入。记录每个非空增量的到达时刻（monotonic）。
- A 先发；收到至少 50 个非空增量后，才发第一个 B。
- 每个 B 发出前检查 A 的运行时长：若当前 A 自发出起已超过 300 s，先关闭当前 A 的连接，等 `/v1/stats` 的 `requests.active` 回到 0，再发一个同样的 A，收到 50 个非空增量后再发 B。依据：按 ≤ 40 tok/s，300 s 内最多输出 12,000 个 token，剩余 ≥ 4,384 个，足够覆盖最长的事件（约 20 s）；不用增量个数判断，因为一个增量可能含多个 token。**不得在 B 在途时让 A 结束**；若仍发生，该事件记为 `invalid_a_ended`，不补测。

### 3.2 事件 B（13 个，顺序固定）

1. T2 第 0–11 轮：使用任务 A 已冻结的 12 个 payload（`SRV/development/ophak_task_a_20261011/inputs/t2_round_XX.json`，按 `INPUTS.json` 校验 SHA），原样字节发送（payload 自带 `max_tokens` 32）。**不得加冷标记。**
2. L64：`SRV/development/gemini_oom_hybrid_20261011/inputs/L64.json`，先校验原文件 SHA256 为 `261d50af3092dfabd20514e6ad06393be4e5265a1e2b9d95c158746946356618`，再只把 `max_tokens` 从 2048 改为 32，其余字段不改，**不加冷标记**（window01 的 L64 加过冷标记，这里不加）。L64 放在最后。

每个事件：等上一个 B 收到 usage，且 A 自上一个 B 结束后又收到至少 30 个非空增量，再发下一个 B。

### 3.3 每个事件记录

- B 的发出时刻 `t_d`、首个非空增量时刻 `t_f`（定义同 3.1）、usage（`prompt_tokens`、`cached_tokens`）。
- A 在 `[t_d − 2 s, t_f + 2 s]` 内全部非空增量的到达时刻。
- **停顿 G**：A 在该区间内相邻两个非空增量之间的最大间隔。
- **零输出检查**：`(t_d + 0.4 s, t_f − 0.2 s)` 内 A 的非空增量个数。起点取 0.4 s 而不是更早，是因为生产的分词与反分词在同一进程（`num_tokenizer` 默认 0）：B 分词期间 A 的输出会先被压住、再集中到达；实测渲染加分词 L64 为 0.126 s、T2 为 0.02–0.04 s。
- 生产 serve.log 在该事件期间新增的 `Prefill batch` 行（`#new-token`、`#cached-token`）。路径取 `production.active.json` 的 `log` 字段。
- **混入检测**：事件期间每 0.5 s 读一次 `/v1/stats`，记录 `requests.active` 与 `requests.completed`。`active` 从请求到达起计到完成为止（`server/stats.py`），排队的也算。
- 每个事件前后各采一次 `nvidia-smi` 显存，只报告。

## 4. 前置检查（开测前全部满足，否则停下告诉主会话）

1. 生产 `/health` 为 `serving`，`backend_epoch == 0`，`restart_attempts == 0`。
2. `/v1/stats`：60 秒内每 5 秒读一次，`requests.active` 全为 0，`requests.completed` 不变。
3. **缓存状态**：`requests.completed == 2` 且 `requests.prompt_tokens_total == 8769`，即 22:46 之后只有两条冒烟请求。冒烟长请求与 T2 第 0 轮共享 8,193 个 token，T2 第 0 轮的预期结构（cached 448）就是按这个状态算的；若数字不同，说明期间有其他请求，必须由主会话重算后再放行。
4. `plan/OPHAK_TASK_S_STOP.md` 本地与服务器都不存在。
5. 没有其他 GPU 测试在跑：`pgrep -f task_a_runner` 为空；`/data2/_shared/gpu.lock` 的内容与 `production.active.json` 中 `gpu_owner.lock_token` 逐字相同。

## 5. 停止规则（都不重试）

- 任何 OOM、worker 退出标记（匹配规则同任务 A2 §3 第 2 条），或 `/health` 不为 `serving`：立即关闭全部我方连接，记录，发消息给主会话。不要手动干预生产的自动恢复。5 分钟后 `/health` 仍不为 `serving`：在协调日志标"紧急"并再发一次消息；是否以及如何恢复 481，由主会话另发补充（任务 B 的停服起点也随之调整）。
- 混入：任一读数 `requests.active` 大于我方在途请求数，或事件前后 `requests.completed` 之差不等于我方在该区间完成的请求数，该事件记为 `contaminated`，照常继续（T2 的缓存状态无法重来，不补测）。
- 总时限 15 分钟。

## 6. CPU 演练（先做，交付 `WORK_S/REHEARSAL_S.json`，0444）

用桩服务模拟 A 的持续输出、B 的预填停顿和 `/v1/stats`，跑通全流程。另做四项反向对照：

- (a) 桩服务的 A 时钟超过 300 s：工装在发 B 之前关闭旧 A、发新 A，并在 50 个增量后再继续；
- (b) 桩服务在 B 预填期间让 A 仍有输出：零输出检查能标出非零；
- (c) 桩服务在某事件期间让 `active` 比我方在途数多 1：该事件被标为 `contaminated`；
- (d) 桩服务把 `completed` 报成 3：前置检查 3 拒绝开测。

工作目录 `SRV/development/ophak_task_s_20261011/`（WORK_S），运行输出 `SRV/runs/dev_ophak_task_s_20261011/`。就绪后在协调日志写"op-hak：任务 S P1 就绪"并发消息给我；**等主会话写"任务 S 放行"再在生产上测。**

## 7. 判读（全部取自预登记 v2）

| 项 | 判据 | 读法 |
|---|---|---|
| 结构 | 一级：该事件 `Prefill batch` 行数（段数）等于 `segments_expected` 的段数；二级：`#cached-token` 与各段长度也相同 | 一级相同才进入下面的停顿判读；二级全同记"结构全中"；一级不符：该事件只报告 |
| 单事件 | 停顿 G 落在该事件的 `stall_band_s` 内 | 逐个标"在区间内 / 不在" |
| 总判 | n = 进入停顿判读且未混入的事件数，k = 其中在区间内的个数 | k ≥ ceil(11n/13)：**成立**；k ≤ floor(6n/13)：**不成立**；其余：**部分成立**；n < 9：只报告不判 |
| 零输出 | 每个事件的零输出计数 | 全部为 0：成立；否则写出哪些事件、多少个 |
| 显存 | 事件前后的显存 | 只报告 |

## 8. 报告

`WORK_S/RESULT_S.md`（0444）：逐事件一张表（事件、段数与各段长度、cached、预测 P、停顿 G、G/P、是否在区间内、零输出计数、是否 contaminated / invalid_a_ended），加 §7 的结论和开测前的 `/v1/stats` 读数。完成后在协调日志记一行，并发消息给 freetoken-06。

## 9. 主会话下发前自检

| # | 清单项 | 本指令的情况 |
|---|---|---|
| 1 | 终点指标 | 直接测用户感受到的停顿（A 的输出间隔） |
| 2 | 预测是否事先写死 | T2 的 12 个预测取自 window02 实测首 token（非空增量口径）；L64 为推导值（window01 总耗时减解码；该记录的 `first_token_time_s` 是空首分片，不可用），并用冷预填吞吐 4,700–5,100 tok/s 独立核对为 12.55–13.62 s，落在区间内。已封存 |
| 3 | 预期结构按生产实际状态算 | 用生产 tokenizer 按"冒烟短、冒烟长、A、T2 0–11、L64"的真实顺序重放（`stall_seq_sim.py`），先复现了冒烟的两条实测切段 [512]、[512, 7745]。结论：冒烟长请求与 T2 第 0 轮共享 8,193 个 token，T2 第 0 轮为 cached 448、[64, 11931]（v1 误写 cached 0）；L64 为 cached 0、[22272, 41728]；其余 11 轮与 v1 相同 |
| 4 | 目标负载 | T2 真实 Agent 轨迹 12 轮，加一个 64K 请求；没有用 87K / 95K，以避开已知的 OOM 风险 |
| 5 | 判据有无停止条件 | 有（§5、§7）；总判的分母随混入和结构不符自动缩小，n < 9 不判 |
| 6 | 计时口径 | 非空增量口径与 A2 相同；零输出窗口起点考虑了共享分词进程（实测分词 ≤ 0.13 s） |
| 7 | 混入检测 | `active`、`completed` 的语义已从 `server/stats.py` 读码核实，写成精确规则 |
| 8 | 合理性 | 若两段事件的 G 只有约一遍（2.8 s），说明两段之间插了解码，与读码结论不符，照实报告 |
| 9 | 生产风险 | L64 在 window01 的预热服务上通过过（显存 21,792 → 23,186 MiB）；首次 OOM 即停；自动恢复在开测前核对为未用过；恢复不了由主会话处理 |
| 10 | 今天的教训 | 不加冷标记；首分片可能是空包；worker 退出即时识别；混入检测；失败不重试 |
| 11 | 对用户的影响 | 约 6 分钟内两个运行槽被占，局域网用户请求会排队；并发 2，不是压力测试 |
