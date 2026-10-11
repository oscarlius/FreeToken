# Codex 指令：D11 前置测量 P0——另一路预填时，当前这一路会卡住多久（2026-10-11，主会话）

- **用户裁定**（2026-10-11 约 11:33，主会话提问后用户选择）：D11 先做前置测量，测完再决定是否投入 15–25 人日。
- **本指令只做测量**：
  - 不开发 D11，不建 D11 分支，不改 FreeToken 引擎代码；
  - 不起停任何服务，不改 481 的配置；
  - 不推送，不启动 Ollama，不改论文。
- **相关卡片**：`plan/02_开发任务/D11_机制D6_遍内插解码_后置.md`；T14 结论见 `plan/01_测试与调研/results/T14-S-004_20261003.md`。

---

## 0. 为什么先测，而不是直接开发

D11 想解决的问题是：一路会话在做预填时，另一路正在输出的会话会被整段卡住；D11 想把这个停顿压到 1 秒以内。它不能当作单独模块开发，原因有四条：

1. **收益没有实测依据。** 卡片要求的前置基线（T05 中"最长停顿与干扰期速度"）一直没有测。E2-R045 实际只测了短提示的两路解码速度。
2. **会改动核心路径。** 涉及的地方包括：预填的层循环（`models/qwen4_exp/model.py:148` 的 `forward_layer_major`）、`core.py:223` 禁止嵌套 `forward_batch` 的断言、整模型 CUDA Graph、卸载缓存分区、调度器。这些文件和 D05、D09 修复、hybrid 的改动重叠，现在开发，日后合并必然冲突。
3. **核心思路已有前人工作。** T14 结论：在层边界插入解码，已被 Layered Prefill 做过；D11 只剩卸载带宽、GDN 状态、CUDA Graph 冲突三处可以算作新内容。
4. **D11 有代价。** 每插入一步解码，预填就被拉长一点，被插入的那一路首字时间会变长。

## 1. 主会话的推算（**推算，未实测**，本测量就是为了核实它）

| 项 | 推算 | 依据 |
|---|---|---|
| 热轮次的停顿（真实 agent 每轮新增 188–2,389 token） | 约 3–4 s | offload 下 1.2K 提示的 TTFT 为 3.65–3.96 s（retry2 实测）。短后缀的一遍预填受搬运限制，48 层专家都要搬一遍 |
| 冷启动的停顿（87K） | 约 11–12 s | G_seed_real round-00 录制的 SSE：首尾 `created` 相差 16 s，扣掉 124 token 的解码时间 |
| D11 理想情况下的停顿 | 约 0.1 s | 一遍预填时间 ÷ 48 层，加一个解码步 |
| D11 对另一路的代价 | 首字时间约 +1.7 s（+55%） | 48 个层边界各插一步解码，每步约 35 ms |

推算的读法：D11 能把"卡 3 秒"变成"几乎不卡"，代价是另一路的首字时间变慢；它**不提高总吞吐**。值不值得做，取决于实测的停顿到底有多长。

## 2. 下发前自检

| 项 | 核对结果 |
|---|---|
| 负载内容（检查内容本身） | **B 路**（触发预填的一路）用 `E2-R046g/G_seed_real` 的 round-00 到 round-06：<br>• 真实 agent 会话；<br>• round-00 只有 1 条 user 消息，345,089 字符的代码加一个真实问题，87,100 token；<br>• 之后每轮新增的未缓存 token 依次约为 288、188、1,871、1,417、252、2,389（录制时 prompt−cached）。<br>**A 路**（被卡的一路）用 X 第 0 条：<br>• 21 行，只有 12 行不同，是模板化文本；<br>• 只用来"保持一路在解码"，停顿的大小由 B 的预填决定。<br>以上两点都要在报告中注明 |
| KV 容量 | 生产配置 `--kv-reserve-tokens 98304`，两路上下文之和不能超过这个值，否则 B 要排队，测出来的是另一回事：<br>• 冷事件：87,100 + A 的 2,715（1,179 + 1,536）= 89,815 ✓<br>• 最大的热事件 round-06：93,269 + A 的 1,563（1,179 + 384）= 94,832 ✓<br>**round-07（95,352）余量只有约 1.4K，不用** |
| 流式粒度 | 录制的 SSE 中，124 个 token 对应 107 个数据分片，大致一个 token 一片。delta 字段可能是 `reasoning_content`、`content` 或 `tool_calls`，计算间隔时**三种都要算**，只看 `content` 会测出假停顿 |
| 冷与热的控制 | 每条轨迹在 `messages[0].content` 前面加一行唯一标记（见 3.2）。这样各轨迹之间不共享缓存，同一轨迹内各轮又能正常命中缓存。最前面的 tools 段约 228 token 仍会跨轨迹命中，可以忽略。用 `usage.prompt_tokens_details.cached_tokens` 核实 |
| 防止混入他人请求 | 服务端 `/v1/requests` 是请求环（`server/request_ring.py`，字段：`ts, method, path, status, duration_ms, prompt_tokens, completion_tokens, ttft_ms…`）。已读码核实：<br>• `/v1/chat/completions`、`/v1/messages`、`/v1/responses` 由 `generation.py:_record_generation` 在**请求结束时**各记 1 条，`prompt_tokens` 有值；<br>• `/v1/completions`、`/generate` 由中间件记录，`prompt_tokens` 为 None。<br>因此：每个事件结束后核对一次；全部跑完后，再按每条记录的 `ts − duration_ms` 回溯复查。后者用来抓"与我们重叠、但更晚结束"的外来请求（见 3.2 第 5、7 步） |
| 真实入口演练 | 先用 CPU 上的桩服务端到端跑一遍真实客户端代码，包括正向对照（注入已知停顿，必须测出来）和反向对照（注入外来请求，必须识别出来），之后才能连生产 |
| 压力测试 | 不算：并发 ≤ 2，总时长 ≤ 30 分钟。服务不停，只在生产 481 上发 30 个事件 |
| 关键路径上的人工环节 | 没有：GPU 测量的放行条件全部是机械检查；主会话否决用 STOP 文件 |

---

## 3. CPU 开发（现在开始；不占 GPU，不连生产）

- **服务器代码目录**：`/data2/FreeToken/development/d11_p0_stall_20261011/`（本地镜像：`freetoken/development/d11_p0_stall_20261011/`）。
- **输出目录**：`/data2/FreeToken/runs/dev_d11_p0_20261011/`。
- **Python 环境**：`/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python`（openai 2.54.0、pytest 9.1.1）。桩服务只用标准库。
- **工具选择**：遵循"开源优先、自研只做薄适配"——客户端直接用 OpenAI SDK 的流式接口，不自己写 HTTP 客户端。

### 3.1 `freeze_inputs.py`：冻结输入

- 把 X 第 0 条的 `text`，以及 `E2-R046g/G_seed_real/round-00` 到 `round-06` 的 `.payload.json`，复制到 `inputs/`。生成 `INPUTS.json`，记录每个文件的源路径和 SHA256。
- 复制时断言以下内容事实，任何一项不符就报错退出：
  - round-00：`messages` 只有 1 条，role=user，内容 345,089 字符；`tools` 有 3 个。
  - round-01 至 round-06 的 `messages[0]` 与 round-00 的 `messages[0]` 完全相同（主会话已核实）。
  - X 第 0 条长 6,356 字符。
- 同时从各轮的 `.api.json` 读出录制时的 `usage.prompt_tokens` 和 `cached_tokens`，写入 `INPUTS.json`。这两个值供两处使用：
  - 运行前的 KV 容量断言（见 3.4）；
  - 运行后的合理性检查（见第 5 节）。

  X 第 0 条的 prompt_tokens 记为 1,179（retry2 实测）。

### 3.2 `stall_probe.py`：测量客户端

**请求构造**

- **A 路**：`messages=[{"role":"user","content": X0}]`，`temperature=0`，`stream=True`，`stream_options={"include_usage": True}`，`extra_body={"ignore_eos": True}`。`max_tokens` 冷事件取 1536，热事件取 384。
- **B 路**：使用冻结的 payload 原样发送，包括 `messages`、`tools`、`model`、`temperature`。只改两处：
  - `max_tokens=16`：让 B 的解码尽量短，使干扰期基本等于它的预填；
  - 在 `messages[0].content` 最前面加一行 `[d11-p0 run=<run_id> traj=<t>]\n`，同一轨迹的各轮必须完全一致。

**每个事件的流程**

1. 用 `GET /v1/requests?since=10**12` 取当前的 `next_cursor`。
2. 启动 A。A 收到第 64 个 delta 分片时发送 B。这里的分片指 `choices[0].delta` 中含 `content`、`reasoning_content` 或 `tool_calls` 任一字段的分片。
3. 记录时间（全部用 `time.perf_counter_ns()` 计时）：
   - A 每个分片的到达时间；
   - B 的发送时刻、首个分片时刻、结束时刻；
   - 两路的 `usage`（`prompt_tokens`、`completion_tokens`、`cached_tokens`）。
4. 等两路都结束。单个请求的超时是 600 s。
5. 再从第 1 步的游标取 `/v1/requests`。生成类路径（`/v1/chat/completions`、`/v1/completions`、`/v1/messages`、`/v1/responses`、`/generate`）必须正好 2 条，且 `prompt_tokens` 与我们两路的 `usage.prompt_tokens` 一致；否则该事件记为 `contaminated`，不计入结果。
6. 事件之间间隔 2 s。
7. 全部事件结束后，从运行开始时的游标起，再取一次完整的请求环（容量 512，本次约 60 条）。对每一条不属于我们的生成类记录，用 `ts`（UTC，精确到秒）减去 `duration_ms` 得到它的时间区间；凡是与该区间有重叠的事件，前后各放宽 1 s，一律追加标记为 `contaminated`。

**每个事件的指标**

| 指标 | 定义 |
|---|---|
| `a_base_itl_ms` | A 第 16 到第 64 个分片之间间隔的中位数 |
| `a_max_gap_ms` | 从 B 发送到 B 首分片后 1 s，这段时间内 A 相邻分片间隔的最大值 |
| `stall_ms` | `a_max_gap_ms − a_base_itl_ms` |
| `a_interf_tps` | 从 B 发送到 B 首分片之间，A 收到的分片数 ÷ 时长 |
| `b_ttft_ms` | B 的首字时间 |
| `b_uncached` | `prompt_tokens − cached_tokens` |

**计划**（`--plan full`，按以下顺序执行）

| 序号 | 事件 | 用途 |
|---|---|---|
| 1 | A 单独 ×2（384 token，不发 B） | A 的基线速度；自然状态下的最大间隔 |
| 2 | 轨迹 t0：只有 B，round-00 到 round-06 | 纯预填时间，没有竞争 |
| 3 | 轨迹 t1、t2、t3：每条依次是 round-00（冷事件）加 round-01 到 round-06（热事件），每个事件都配一个 A | 停顿的主要数据 |

合计：2 + 7 + 21 = 30 个事件。预计 10–15 分钟，**硬上限 30 分钟**。

另外提供 `--plan smoke`：只跑 1 个 A 单独事件，64 token。

**停止规则**（都不重试）

| 情况 | 处理 |
|---|---|
| 任一请求出错或超时 | 立即停止，写 `terminal.json` |
| 运行中（第 5 步）判为 contaminated 的事件累计 ≥ 3 个 | 说明生产正在被使用，立即停止并回报。当天不再重跑 |
| 第 7 步回溯复查后，contaminated 总数 ≥ 3 | 不用停止（运行已经结束）。`terminal.json` 分类记为 `production_busy`；照常报告未受污染的事件，但这次运行不算一次完整测量 |
| 总时长超过 30 分钟 | 停止 |

**输出**

- `events.jsonl`：每个事件一行，包括原始分片时间序列。
- `summary.json`：按事件类型分组的中位数和最小/最大值。
- `terminal.json`

### 3.3 `stub_server.py`：CPU 桩服务（只用于演练）

- 只用标准库（`http.server.ThreadingHTTPServer`）。
- 提供以下接口：
  - SSE 格式的 `/v1/chat/completions`：每个 token 发一个 `reasoning_content` 分片，最后发 `usage`，`cached_tokens` 可配置；
  - `/v1/requests`：请求环，语义与生产相同；
  - `/health`。
- 请求环的记录方式与生产一致：每个聊天请求在结束时记 1 条，`path=/v1/chat/completions`，`prompt_tokens` 与该请求 `usage` 中的值相同。
- 桩服务的 `usage.prompt_tokens` 按以下规则返回：
  - 带 tools 的请求：`INPUTS.json` 中该轮的录制值，再加 16（模拟标记行）；
  - 其他请求：1,179。
- `cached_tokens` 规则：round-00 返回 0；之后各轮返回"上一轮录制的 prompt_tokens，向下取整到 64 的倍数"。
- 可配置项：
  - 每个 token 的间隔；
  - 模拟预填：第二个请求到达时，暂停正在输出的那一路。只有 1 条消息且内容超过 100,000 字符的请求（冷事件）暂停 D_cold 秒，其他请求暂停 D_warm 秒；
  - 在指定事件期间，往请求环注入一条外来的生成请求记录。

### 3.4 `test_stall_probe.py`：单元测试

至少覆盖以下内容：

- 指标计算：间隔、最大间隔、中位数；
- 三种 delta 字段都会被计数；
- `usage` 解析；
- contaminated 判定：多 1 条、少 1 条、`prompt_tokens` 不一致；
- 停止规则；
- KV 容量断言：任何事件的两路上下文之和超过 98,304 时，拒绝运行。

### 3.5 真实入口演练（必须做；用桩服务，地址 127.0.0.1:18300）

| 演练 | 桩服务配置 | 必须得到的结果 |
|---|---|---|
| R1 正向对照 | token 间隔 40 ms；D_cold = 3.0 s，D_warm = 1.0 s | 冷事件 `stall_ms` = 3000 ± 10%，热事件 = 1000 ± 10% |
| R2 反向对照 | 分两种情况：<br>(a) 在第 5 个事件期间注入 1 条已结束的外来请求；<br>(b) 注入 1 条"第 6 个事件期间开始、第 8 个事件之后才结束"的外来请求 | (a) 在第 5 步就被识别，运行继续；<br>(b) 在第 7 步的回溯复查中被识别，第 6 至第 8 个事件都标为 contaminated。<br>最终共 4 个 contaminated，`terminal.json` 的分类为 `production_busy`，summary 的计数正确 |
| R3 无停顿对照 | 不暂停 | 所有事件 `stall_ms` < 200 ms |

- 三项都用 `stall_probe.py --plan full` 的真实代码路径，只把 `--endpoint` 换成桩服务的地址。
- 写出 `REHEARSAL.json`：包含三项结果和全部源文件的 SHA256，设为 0444。

### 3.6 交付（CPU 阶段）

1. 写 `CPU_READINESS.md`，内容包括：文件清单与 SHA；pytest 输出；R1–R3 结果；第 2 节内容核对项的实际输出。
2. 更新 `freetoken/README.md` 的工具索引（新增一行，指向本目录）。
3. 在协调日志写"D11-P0 CPU 就绪"，附上 SHA。

---

## 4. 生产测量（主会话预授权，满足条件即可执行，**不必等主会话回复**）

**放行条件**（必须全部满足，任何一项不满足就不跑，记录原因）：

1. 时间 ≥ 2026-10-11 18:00。避开局域网用户的工作时间。
2. KIMI 已写出 `development/kimi_phase2_20261011/EVENING_RESULT.md`。
3. `/data2/FreeToken/run/production.active.json` 的 `approval_id` 为 `RESTORE481-MORNING-20261011-09`，`/health` 返回 `status=ok` 且 `maintenance=serving`。
4. 除生产服务外，没有其他 `ft serve` 进程；GPU 锁属于生产。
5. 本地 `plan/D11_P0_STOP.md` 和服务器 `/data2/FreeToken/plan/D11_P0_STOP.md` 都不存在。
6. `REHEARSAL.json` 中 R1–R3 全部 PASS，且源文件 SHA 与演练时一致。
7. 最近 120 s 内，`/v1/requests` 中没有生成类请求，即服务空闲。

**执行**：客户端在 9 号机本机运行，连接 `http://172.16.108.9:8095`（S 类口径）。

```bash
cd /data2/FreeToken/development/d11_p0_stall_20261011
$PY stall_probe.py --endpoint http://172.16.108.9:8095 --plan smoke --out /data2/FreeToken/runs/dev_d11_p0_20261011/smoke01
# smoke 通过（1 个事件，非 contaminated）后：
$PY stall_probe.py --endpoint http://172.16.108.9:8095 --plan full --out /data2/FreeToken/runs/dev_d11_p0_20261011/run01
```

**失败处理**：

- smoke 失败：不跑 full，回报。
- full 的停止规则见 3.2。
- 任何时候都不重试，不改代码后重跑。

## 5. 结果报告与预登记读法

报告写在 `development/d11_p0_stall_20261011/RESULT.md`，表格包括：

- 每个事件的 `b_uncached`、`b_ttft_ms`、`stall_ms`、`a_interf_tps`；
- 按冷/热分组的中位数；
- t0（只有 B）的预填时间；
- 被排除的事件及原因。

**主会话按以下规则读结果**（预先登记，测完不改）：

| 量 | 定义 |
|---|---|
| `G_warm` | 18 个热事件 `stall_ms` 的中位数 |
| `G_cold` | 3 个冷事件 `stall_ms` 的中位数 |

**合理性检查**（不满足就记为"异常、待诊断"，不得当作有效结果）：

- A 单独时的速度 ≥ 20 tok/s。同一上下文下，X 单路 offload 实测 30.17 tok/s。
- 冷事件 `cached_tokens` ≤ 512；热事件的 `b_uncached` 与录制值的差在 ±128 以内。
- 冷事件的 `b_ttft_ms` 大于热事件中位数的 2 倍。按推算，冷事件约 11 s、热事件约 3–4 s，比值约为 3；这里不能写成 5 倍，否则正常结果也会被判为异常。
- `G_warm` 与 t0 热事件预填时间的中位数相差在 ±30% 以内。用于确认停顿确实来自 B 的预填。

**D11 价值判定**（交给用户的建议）：

| `G_warm` | 建议 |
|---|---|
| < 1.0 s | 不建议立项：热轮次停顿不到 1 秒，冷启动只发生在会话开始 |
| ≥ 2.0 s | 停顿真实存在且明显。主会话据此算出 D11 理想上限（一遍预填时间 ÷ 48，加一个解码步）和对另一路首字时间的代价，交用户决定是否批准 15–25 人日 |
| 1.0–2.0 s | 同时报告两组数字，交用户决定 |

## 6. 纪律

- 只追加、不覆盖；每一步在协调日志写一行，时间戳为真实的写入时刻。
- 拿不准就停，写明原因，等主会话。
- 不把用户邮箱或任何个人信息发往任何服务。
