# Gemini 指令：D11-P0 停顿基线——另一路预填时，正在输出的一路会卡多久（2026-10-11 晚，主会话）

> 读者是第一次接手这项测量的执行者，下文把环境、约定和每一步都写全了。请**从头到尾读完再动手**。遇到本文没写到的情况，就停下来，在协调日志里写明原因，等主会话处理。
>
> **本文件发出后冻结，不再修改**；如需更正，主会话另发补充文件。
>
> 本指令**取代** `plan/CODEX_D11_P0_STALL_BASELINE_20261011.md`（SHA256 前缀 `7accfbe5`）及其补充 1、补充 2。Codex 没有开始执行；主会话 19:01 已放置 `plan/D11_P0_STOP.md`（本地与服务器一致，SHA256 `18b2c77d…`，0444），按 Codex 原指令第 4 节第 5 条否决 Codex 执行。两份指令的差异见 §1.3。
>
> 本指令下发前经过主会话自审和一次独立审核（`oh-my-claudecode:critic`）。独审提出的 1 个 CRITICAL、2 个 HIGH、2 个 MEDIUM、5 个 LOW，主会话逐条读码核实后全部采纳，处置见 §6。

---

## 0. 角色、环境与红线

### 0.1 角色

- **你**：执行者。负责编写测量工装、在 CPU 上演练、在生产 481 上执行测量、写报告。
- **主会话**：审核者。负责写指令、复核结果、按 §5 的预登记规则读结果。
- **用户**：拍板人。

本测量已获用户批准：

- 10-11 11:33，用户选择"D11 先做前置测量，测完再决定是否投入 15–25 人日"；
- 10-11 19:00 前后，用户要求改由 Gemini 执行。

### 0.2 环境

| 项 | 值 |
|---|---|
| 测试服务器 | `172.16.108.9`。从办公电脑用 `ssh 9 '<命令>'` 执行，登录用户 dell |
| 本地仓库 | `D:\00.开发\2026\03-模型实验\freetoken\freetoken\`（下称 LOCAL）；服务器对应 `/data2/FreeToken/`（下称 SRV） |
| Python | 工装、桩服务、单测一律用 `/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python`（下称 `$PY`；openai 2.54.0、httpx 0.28.1、pytest 9.1.1）。桩服务只用标准库 |
| 发布版代码（只读） | `SRV/wt/release-e2/python/freetoken/`，提交 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| 生产服务 | 481，`http://172.16.108.9:8095`，供局域网用户使用。19:31 时的状态：<br>• 审批号 `RESTORE481-MORNING-20261011-10`，service pid 2621413；<br>• `backend_epoch=0`、`restart_attempts=0`；<br>• 观察器 pid 2635719，运行到 2026-10-12 09:00。<br>今晚 D09 窗口（`plan/GEMINI_D09_ENABLE_20261011.md`）结束后会以 `-11` 恢复。两个审批号对应同一发布版，启动参数相同 |
| 生产日志 | 读 `SRV/run/production.active.json` 的 `log` 字段（-10 时为 `SRV/runs/production/RESTORE481-MORNING-20261011-10/serve.log`）。**不要写死路径** |
| 生产关键参数 | `--moe-strategy offload --memory-ratio 0.88 --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens 98304 --max-seq-len-override 98304 --max-prefill-length 4096 --prefill-layer-major --enable-special-token-ckpt --enable-cache-report --reasoning-parser qwen3 --tool-call-parser qwen3_coder`（全文见 `production.active.json` 的 `argv`） |
| 硬件 | 1 张 RTX 4090（24 GB）；双路 Xeon Silver 4310（48 线程）；内存 251 GB |

### 0.3 产出目录

| 用途 | 服务器 | 本地镜像 |
|---|---|---|
| 代码、文档 | `SRV/development/gemini_d11_p0_20261011/`（下称 WORK） | `LOCAL/development/gemini_d11_p0_20261011/` |
| 运行输出 | `SRV/runs/dev_gemini_d11_p0_20261011/`（下称 RUNS） | 不必镜像 |

不要在别人的目录里写文件。**尤其不要创建** Codex 原指令的目录 `SRV/development/d11_p0_stall_20261011/` 与 `SRV/runs/dev_d11_p0_20261011/`。

### 0.4 红线（任何情况下都不得违反）

1. 不推送代码，不启动 Ollama，不改论文（`paper/`）。
2. **不停止、不启动、不重启 481**，不动 `/data2/_shared/gpu.lock`，不用 kill 结束任何不属于你的进程。本测量只作为普通客户端向 481 发请求。
3. 不修改发布版代码树、模型目录、他人的工装与证据目录；只允许读取和按字节复制。
4. 任何一步失败都**不重试**，按 §3.2.8 和 §4.3 的失败去向处理。"等待生产空闲"（§4.1）不算重试。
5. 不把用户邮箱或任何个人信息发给任何服务。
6. 在 Windows 上写要拷到服务器的 `.py`、`.json` 文件时，用 LF 换行（Python 写文件用 `newline="\n"`）。
7. **所有访问 `172.16.108.9` 的 HTTP 请求都必须绕过代理**（原因见 §1.3 第 3 条）：
   - OpenAI SDK：`OpenAI(base_url=..., api_key="EMPTY", max_retries=0, http_client=httpx.Client(trust_env=False, timeout=600))`；
   - 标准库：`urllib.request.build_opener(urllib.request.ProxyHandler({}))`。
8. **生产测量进行期间，服务器上不跑任何别的任务**：pytest、桩服务演练、编译、大文件拷贝都要在测量开始前结束。D09 窗口进行期间，也不在服务器上跑本指令的 pytest 与演练。
9. **D11-P0 与 D09 窗口不得交错**（§2.1）。

### 0.5 协调日志

每完成一步，在 `LOCAL/plan/COORDINATION_LOG.md` 末尾追加一行：

```
- <时间戳> Gemini：<步骤号> <结果>（附关键 SHA256 前 12 位）
```

时间戳一律用服务器真实时间：`ssh 9 'date "+%Y-%m-%dT%H:%M:%S+08:00"'`。不要估计，也不要事后补写。

---

## 1. 背景

### 1.1 要回答的问题

D11（论文 M3，"遍内插解码"）想解决的问题是：会话 B 在做预填时，正在输出的会话 A 会被整段卡住；D11 想把这个停顿压到 1 秒以内。

主会话已推演过 D11 的代价与吞吐上限（`plan/D11_DECISION_20261011.md`），结论是"现在不做"。立项条件之一是**本测量实测 G_warm ≥ 2 s**。卡片要求的前置基线（"最长停顿与干扰期速度"）至今一次都没测过，论文的核心假设 H0 也因此一直缺少实测。

本次测量的对象，是生产 481 上真实 agent 会话（G_seed_real，上下文 87K–93K）的两类停顿：

- **热事件**：B 是同一会话的下一轮。只有新增的 188–2,389 个 token 要预填，其余命中前缀缓存。
- **冷事件**：B 是一个新会话的第一轮，87,100 个 token 全部要预填。

### 1.2 预测（**推算，未实测**；只用于事后对照，不是判据）

**热轮次的预填是两段，不是一段。** 录制日志（`/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/serve.log` 第 44–49 行）中，round-01 先跑 `anchor_cap` 段（64 token），再跑 `continuation` 段（224 token）：

- 每段 `wall` 约 2.70 s；
- 每段 H2D 59.62 GiB，48 层的专家几乎都搬了一遍。

后面各轮也是同样的两段。这正是 v3.2 说的"两遍"，也是今晚 D09 启用路径要去掉的那一遍（D09 指令预测热轮首 token 从约 5.3 s 降到 2.8 s）。所以本测量测到的是**不开 D09 时**的停顿基线。

| 量 | 推算值 | 依据 | 依赖的未验证前提 |
|---|---|---|---|
| A 单独的速度 | 29–30 tok/s（间隔约 34 ms） | window01 S1 offload 单路实测 29.68 | — |
| G_cold | 18–19 s | window01 S1 L87（87,128 token）首字 18.62 s；录制 SSE 中 role 包到首个 token 相差 19 s | — |
| G_warm（单个最长间隔） | **两种可能**：<br>• 两段之间不给 A 解码：约 5.4–6.5 s（两段各约 2.7 s，加上 B 的分词）；<br>• 两段之间插入了 A 的解码：约 2.7–3.5 s，同时 `a_extra_ms_sum` 约 5.4–6.5 s | 上面两段的录制数据。独审读码：调度器预填优先（`scheduler.py:1041-1046`）。`num_tokenizer=0` 时分词与反分词同一进程串行（`args.py:88-90`），B 分词期间 A 的输出会积压 | 两段之间是否插入解码，本次没有读码定论；测量会用 `a_gaps_over_3x` 与日志段数回答 |
| 冷热首字时间之比 | 约 3 倍（18.6 s 对 5.5–6.5 s） | 同上 | — |

### 1.3 与 Codex 原指令的差异（主会话核查与独审发现）

| # | 项 | Codex 原指令 | 本指令 | 原因（已核实的事实） |
|---|---|---|---|---|
| 1 | **有效分片的定义** | 含 `content`、`reasoning_content`、`tool_calls` 任一字段 | 三者之一**非空** | 生产的第一个 SSE 包是 `{"delta":{"role":"assistant","content":""}}`，请求一到就立即发出。录制的 round-00 中它比首个 token 早 19 s。按原定义，B 的"首分片"约等于发送时刻，停顿窗口缩到约 1 s，**19 s 的停顿会被整段漏掉** |
| 2 | 防混入 | 请求环 + `ts − duration_ms` 回溯 | `/v1/stats` 的实时 `active` 与累计 `completed`（C1–C3）为主，请求环（C4）为辅 | `/v1/completions` 与 `/generate` 由中间件在处理函数返回时记录（`server/api_server.py:517-545`），流式请求的 `duration_ms` 只有 3–5 ms；今晚冒烟的两条就是 3 和 5 ms，回溯会漏。`active` 在 `new_user` 时加入（`api_server.py:265`，含排队请求），收到 finished 时移出（`:298`） |
| 3 | 代理 | 未提 | 必须绕过（红线 7） | 服务器 shell 环境有 `http_proxy=socks5://…`。`no_proxy` 写的是 `172.16.0.0/12`，Python urllib 不认 CIDR，主会话预演时直接报 `unknown url type: socks5`。httpx 默认也读环境变量 |
| 4 | SDK 自动重试 | 未提 | `max_retries=0` | openai 2.54.0 默认 2 次，出错时会把 87K 请求自动重发 |
| 5 | **OOM** | 未考虑 | 预热阶梯；**首次 OOM 即停** | 今晚的新证据：生产配置下 87K 级冷请求 4 次里 OOM 了 2 次。481 每个进程**只有 1 次自动恢复额度**：`api_server.py:1234` 写死 `max_restarts: 1`，`supervisor.py` 的计数不清零；第 2 次 OOM 后状态变为 failed，不会自动恢复。另外，OOM 时 `fail_dispatched_for_oom`（`api_server.py:364-379`）绕过 `stats.observe`，恢复后 `active` 会永久多算。详见 §3.2.5 |
| 6 | 计划 | t0（只有 B）放最前，共 4 次 87K 冷预填 | 预热阶梯放最前，**删去 t0**，只剩 3 次冷预填 | 首次 OOM 即停时，每多一次冷预填都可能让整个运行提前结束。t0 原本只是交叉核对，改用生产日志中的 `Prefill batch` 行代替 |
| 7 | 合理性检查 | `G_warm` 与 t0 热预填时间的中位数相差 ±30% | 改为物理上界：单事件停顿 ≤ B 首字时间 + 500 ms；比值只做标记 | B 的分词与 A 的解码会互相影响，比值没有可靠的预期区间 |
| 8 | 热、冷事件推算 | 热 3–4 s，冷 11–12 s | 热 5.4–6.5 s（或拆成两段），冷 18–19 s | 见 §1.2 |
| 9 | 放行条件 | 等 18:00、等 KIMI 的 EVENING_RESULT，只认 -09/-10 | 删除前两条；认 -10/-11；新增"自动恢复额度完好"和"无 D09 窗口进程" | 前两条已满足或已无关；后两条见第 5 条与 §2.1 |
| 10 | 进程判断 | `pgrep` | 读 `/proc`，排除自身**及所有祖先进程** | 主会话预演时，`pgrep -f "ft serve"` 把 ssh 的 bash 命令行也算了进去（结果为 3，实际为 1）。独审又发现：工装用子进程调用前置检查时，父进程 `stall_probe.py` 会被当成"另一个 probe"，必然判自己不通过 |
| 11 | smoke 与 full | 分两次启动 | 一次启动（`--plan smoke_then_full`） | D09 窗口开窗前会避让"正在运行的 `stall_probe.py`"。分两次启动，中间的空档可能让 D09 在两次之间停掉 481 |

---

## 2. 总览、顺序与时间

### 2.1 与 D09 窗口的先后

今晚还有一个 D09 停服窗口（`plan/GEMINI_D09_ENABLE_20261011.md`）：停 -10 → T17 与 B 收益 A/B → 用 restore11 恢复为 -11。

**规则**：

1. D11-P0 只在 481 正常服务、且没有 D09 窗口进程时测。前置检查附件会核对这两点：GPU 锁属于生产，且没有 cwd 在 D09 目录下的 `runner.py`、`b_runner.py` 进程。
2. **优先在 D09 开窗之前测。** 万一发生 OOM，481 会用掉唯一一次自动恢复额度；D09 窗口的停服加 restore11 会换一个新进程，额度随之复位。
3. 如果 D09 窗口已经开始，就等它结束、481 以 -11 恢复，并且观察器起来之后再测。测前的前置检查必须全部通过，其中包括"自动恢复额度完好"。
4. 测量期间只有一个 `stall_probe.py` 进程连续运行，D09 指令的 W0 会避让它，最多等 45 min。本测量约 12 min，硬上限 30 min。

### 2.2 阶段与时间

| 阶段 | 内容 | 是否碰生产 | 预计 |
|---|---|---|---|
| P1-1 | 输入冻结 `freeze_inputs.py` | 否 | 10 min |
| P1-2 | 测量工装 `stall_probe.py` | 否 | 40 min |
| P1-3 | 桩服务 `stub_server.py` | 否 | 15 min |
| P1-4 | 单测 `test_stall_probe.py` | 否 | 15 min |
| P1-5 | 真实入口演练 R1–R6 | R6 只读生产的 `/health`、`/v1/stats`、`/v1/requests`；其余只连 127.0.0.1 的桩服务 | 30 min（R1、R3 按 34 ms 间隔跑完整计划，各约 10 min） |
| P1-6 | CPU 就绪记录 | 否 | 5 min |
| P2 | 生产测量：前置检查 → smoke → full（一次启动） | **是**，只发请求，并发 ≤ 2 | 约 12 min；硬上限 30 min |
| P3 | 结果报告 | 否 | 20 min |

**没有人为等待点**：P1-6 完成后，按 §2.1 立即测。不必等主会话回复。主会话如要否决，会放 STOP 文件（§4.1 第 4 条）。

**不属于压力测试**：并发 ≤ 2，持续 ≤ 30 min，不打满任何资源。但有 OOM 风险，影响见 §3.2.5。

---

## 3. P1：CPU 阶段（不发生成请求）

### P1-1 `freeze_inputs.py`：冻结输入（交付 `WORK/inputs/` 与 `WORK/INPUTS.json`）

按字节复制以下文件到 `WORK/inputs/`。复制前后都校验 SHA256，任何一个不符就报错退出：

| 名称 | 源路径 | SHA256 |
|---|---|---|
| X | `SRV/development/d10_reanalysis_20261010/closed_loop_20261010/inputs_X.jsonl` | `f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162` |
| round-00.payload | `/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/round-00.payload.json` | `84b3f62036409f719f759b167836378a7692c90f99b78f342450975a31c8959e` |
| round-01.payload | 同目录 `round-01.payload.json` | `e2f0533a6d8991d923a93a4644bcfcb2fc27cea9d9425043406002e881e41647` |
| round-02.payload | 同上 | `e35ab2cf0c0304d78493b3496dc224cee2ac6bff30e7c39fbdd1fa0e3000c67a` |
| round-03.payload | 同上 | `f2a3e43625e61721e04fbab0073afe46163468bd1018d185c269b7ec9086ef7a` |
| round-04.payload | 同上 | `95266b2baac3864d6a38fdea8626eec6ed2fc73094736e20a4e0b2355c0de921` |
| round-05.payload | 同上 | `bceee9bdf2b4e5ec5dd960a6460ed7acbbe84cd50ab6a41c182b1272f63750be` |
| round-06.payload | 同上 | `f2412ab5cfa31aba1cd4228a2c716d3b1a5b69c0795fe046add9e246cdbd72d0` |
| round-00.api … round-06.api | 同目录 `round-0k.api.json` | 00 `ae64b6deac1be863…`、01 `390379246ce63144…`、02 `16771207fd4498c3…`、03 `a1d31782c534b0c6…`、04 `473cc48d1aab9455…`、05 `02e683ce5ef61c6f…`、06 `2fb3e3271441b5bc…`（按前缀核对，记录全长） |
| L64 | `SRV/development/gemini_oom_hybrid_20261011/inputs/L64.json` | `261d50af3092dfabd20514e6ad06393be4e5265a1e2b9d95c158746946356618` |
| L80 | 同目录 `L80.json` | `274620ae611b5b3e0e78589aff61e90e9ff8de1c469983f1bb7cc7d13939c683` |

**内容断言**（主会话已逐条核实；任何一条不成立就报错退出）：

- **X**：共 2 行；第 0 行是 JSON，字段 `text` 长 6,356 字符。按行切分为 21 行，其中只有 12 行互不相同，是模板文本。A 路只用来"保持一路在解码"，停顿大小由 B 决定。这一点要写进报告。
- **round-00**：
  - `messages` 只有 1 条，role=user，`content` 长 345,089 字符；
  - `tools` 有 3 个，名字依次为 `read_file`、`list_dir`、`search_code`；
  - 其余顶层键为 `max_tokens, model, stream, stream_options, temperature`，其中 `temperature=0`，`model="Qwen3.8-Flash-Next-NVFP4"`。
- **round-01 至 round-06**：`messages[0]` 与 round-00 的 `messages[0]` 完全相同；`tools` 完全相同；消息条数依次为 3、5、7、9、11、13。
- **L64、L80**：各 1 条消息，`content` 分别长 259,713 和 320,524 字符；都带同样的 3 个 tools。

**录制值表**：从各轮 `.api.json` 的 `usage` 读出，写入 `INPUTS.json`，并断言与下表一致。`prompt_tokens_details` 不存在时，cached 记为 0。

| 轮 | 录制 prompt_tokens P | 录制 cached C | 未缓存 U = P − C |
|---|---|---|---|
| 00 | 87,100 | 0 | 87,100 |
| 01 | 87,328 | 87,040 | 288 |
| 02 | 87,484 | 87,296 | 188 |
| 03 | 89,295 | 87,424 | 1,871 |
| 04 | 90,697 | 89,280 | 1,417 |
| 05 | 90,940 | 90,688 | 252 |
| 06 | 93,269 | 90,880 | 2,389 |

另断言规律 `C_k = floor(P_{k−1} / 64) × 64`（k = 1…6，主会话已核实 6 轮全部成立，独审也复核过）。这说明命中位置只到"上一轮 prompt 向下取整到 64"，与上一轮生成了多少 token 无关，所以 B 把 `max_tokens` 改成 16 不影响后续各轮的命中。

**KV 容量断言**（写入 INPUTS.json）：对计划中的每个事件，`B 的录制 P + 64（标记行的上界）+ B 的 max_tokens + A 的 1,179 + A 的 max_tokens` 必须 ≤ 98,304：

| 事件 | 合计 | 余量 |
|---|---|---|
| 冷事件（round-00，A 用 1,536） | 87,100 + 64 + 16 + 1,179 + 1,536 = 89,895 | 8,409 |
| 最大的热事件（round-06，A 用 384） | 93,269 + 64 + 16 + 1,179 + 384 = 94,912 | 3,392 |
| 预热 L80（只有 B） | 80,000 + 64 + 16 = 80,080 | 18,224 |

round-07（95,352）不用：余量只有约 1.3K，而且今晚它在新起的服务上 OOM 过。

### P1-2 `stall_probe.py`：测量工装

#### 3.2.1 客户端

- 用 OpenAI SDK 的流式接口，按红线 7 构造客户端。不要自己写 HTTP 客户端（"开源优先，自研只做薄适配"）。
- `/health`、`/v1/stats`、`/v1/requests` 用标准库访问，按红线 7 构造 opener，单次超时 5 s（C2 采样为 2 s）。
- 全部计时用 `time.perf_counter_ns()`。另记一次 `time.time()` 与 `perf_counter_ns` 的对照，便于与服务端日志对时。
- A、B 各开一个线程；另开一个采样线程（§3.2.4 C2）。

#### 3.2.2 有效分片

一个 chunk 计为**有效分片**，当且仅当 `chunk.choices` 非空，且 `delta = chunk.choices[0].delta` 满足以下任一条：

- `delta.content` 是非空字符串；
- `getattr(delta, "reasoning_content", None)` 是非空字符串。SDK 把这个字段放在 `model_extra` 里，主会话已在 venv-eval 中核实 `getattr` 能取到；
- `delta.tool_calls` 是非空列表。

以下 chunk **不计**：首个 role 包 `{"role":"assistant","content":""}`；结束包 `{"delta":{}, "finish_reason":...}`；usage 包（`choices` 为空列表）。

**usage**：

- 取 `chunk.usage.prompt_tokens` 与 `completion_tokens`；
- `cached = chunk.usage.prompt_tokens_details.cached_tokens`。`prompt_tokens_details` 为 `None` 时记为 0；冷请求就是这样，主会话已核实。

**B 正常结束却没有任何有效分片**时，本事件记为 `b_empty`：事件无效，但不停止运行。

#### 3.2.3 请求构造与每个事件的流程

**A 路**

- `messages=[{"role":"user","content": X0}]`，`model="Qwen3.8-Flash-Next-NVFP4"`，`temperature=0`，`stream=True`，`stream_options={"include_usage": True}`，`extra_body={"ignore_eos": True}`。
- `max_tokens`：冷事件 1,536；热事件与只有 A 的事件 384；smoke 96。
- A 不加标记。这样从第二次起它会命中缓存（1,152 / 1,179），自身的预填很短。

**B 路**

冻结的 payload 原样发送（`messages`、`tools`、`model`、`temperature`），只改两处：

- `max_tokens=16`，让 B 的解码尽量短，使干扰期基本等于它的预填；
- 在 `messages[0].content` 最前面加一行标记：
  - 轨迹请求：`[gemini-d11p0 run=<run_id> traj=<t>]\n`。同一轨迹的 7 轮必须逐字相同，不同轨迹必须不同。这样各轨迹之间不共享缓存，同一轨迹内各轮又能正常命中；
  - 预热请求：`[gemini-d11p0 run=<run_id> warm=<名称>]\n`。

**每个事件的流程**

1. **事件前**：
   - 检查 STOP 文件（§4.1 第 4 条），存在就停止，记为 `vetoed`；
   - 重读 `production.active.json` 的 `approval_id` 与 `gpu.lock` 的 owner，与运行开始时不同就停止，记为 `production_changed`；
   - 执行 C1（§3.2.4）；
   - 记录 `completed_0`、`backend_epoch_0`，以及请求环游标 `cursor_0`：`GET /v1/requests?since=1000000000000&limit=1` 返回的 `next_cursor`，主会话已核实它等于当前总数；
   - 冷事件与预热事件额外记录一次 `nvidia-smi` 显存。
2. **发送**：
   - 配对事件：启动 A；A 收到第 64 个有效分片时，B 线程立即发送 B。`t_Bsend` 取 B 线程调用 `create()` **之前**的时刻；
   - 只有 A 或只有 B 的事件：直接发送。
3. **事件中**：采样线程执行 C2。
4. **等结束**：等全部请求结束（SDK 超时 600 s）。
5. **事件后**：执行 C3、C4（§3.2.4）。冷事件与预热事件再记一次 `nvidia-smi`。
6. **事件间隔**：2 s。

#### 3.2.4 防混入（C1–C4）

| 检查 | 时机 | 做法 | 判定 |
|---|---|---|---|
| **C1 事件前空闲** | 每个事件开始前 | 每 1 s 读 `/v1/stats`，直到连续 2 次 `requests.active == 0`；最多等 120 s | 超时 → 运行停止，记为 `production_busy` |
| **C2 事件中采样** | 从第一个请求发出到最后一个请求结束 | 每 0.5 s 读一次 `/v1/stats`，记录 `(t_send, t_recv, active, completed, maintenance, backend_epoch)`。对每个样本，`n_ours` = 本事件中客户端区间 `[发送, 流结束]` 与 `[t_send − 0.2 s, t_recv + 0.2 s]` 相交的本方请求数 | 任一样本 `active > n_ours` → 本事件 `contaminated`。任一样本 `maintenance != "serving"` 或 `backend_epoch` 变化 → 转 §3.2.5 |
| **C3 事件后核对** | 全部流结束后 | 每 0.5 s 读 `/v1/stats`，直到 `active == 0`（最多 15 s），然后读 `completed_1` | 15 s 内不空闲，或 `completed_1 − completed_0 ≠ 本事件请求数` → `contaminated`。`backend_epoch` 变化 → 转 §3.2.5 |
| **C4 请求环核对** | C3 之后 | `GET /v1/requests?since=<cursor_0>&limit=512`。生成类路径为 `/v1/chat/completions`、`/v1/completions`、`/v1/messages`、`/v1/responses`、`/generate` | 生成类记录数 ≠ 本事件请求数，或这些记录的 `prompt_tokens` 多重集 ≠ 本方 usage 的 `prompt_tokens` 多重集 → `contaminated`。同时把 B 那条记录的 `ttft_ms` 记为 `b_server_ttft_ms`（只作诊断） |

**C2 判定的依据**（主会话读码，独审复核）：

- `active` 在 `new_user` 时加入（`api_server.py:265`，排队中的请求也算）；
- 收到 finished 回复时移出（`:298`），时机在服务端发出结束包之前；
- 所以正常路径下，服务端计到的本方在途数不会超过客户端区间算出的数；
- 0.2 s 的余量用来吸收 `/v1/stats` 调用本身的耗时。

**OOM 之后这个前提不成立**（§3.2.5），所以首次 OOM 即停。

累计 `contaminated` 事件 ≥ 3 → 运行停止，记为 `production_busy`（说明局域网有人在用）。

#### 3.2.5 OOM 的检测与处理（预登记）

**背景数据**（主会话从原始记录核实；生产配置，87K 级冷请求）：

| 情形 | 之前的历史 | 结果 |
|---|---|---|
| 10-10 窗口 A/B | 新起服务的第一条 | 通过 |
| window02 O1、O2（87,379） | 先跑了 X 单路与两路 | 两次都 OOM |
| window01 S1 L87（87,128） | X 若干次，然后 L64 → L80 阶梯 | 通过（显存升到 23,784 MiB） |
| window01 S2 L95（95,352） | 新起服务 | OOM |

当前的 481 是 18:20 新起的，只跑过 2 条冒烟请求，显存 22,454 MiB。本计划共有 3 次 87K 冷预填（t1、t2、t3 各一次）。

**481 的 OOM 恢复只有 1 次额度**（主会话读码核实）：

- `server/api_server.py:1234` 写死 `"max_restarts": 1`；`server/supervisor.py` 中的 `attempts` 在进程生命周期内不清零。
- 第 1 次 OOM：整模型重载约 235 s，期间服务不可用，之后 `backend_epoch` 变为 1。
- 第 2 次 OOM：进入 `_on_failure`（`api_server.py:1187-1199`），状态置为 `failed`，`/health` 返回 `status=error`。所有请求都得到 503，**直到有人手动重启为止**。
- 另外，OOM 时 `fail_dispatched_for_oom`（`api_server.py:364-379`）把终止回复直接写进 `ack_map`，不经过 `stats.observe`。在途请求因此不会从 `active` 中移出，**恢复后 `/v1/stats` 的 `active` 会永久多算**，C1 与前置检查的"当前空闲"门从此失效。

**降低风险**：先发 L64、L80 两条只有 B 的预热请求（不计成绩），复现 S1 通过时的历史。这只是 1 例证据支持的经验做法，不保证有效。

**检测**——以下任一情况都判为 `oom`：

- 请求抛出 `openai.APIError`（含其子类 `APIConnectionError`、`APITimeoutError`），且消息中含 `out of memory` 或 `worker_restarting_after_oom`。SDK 遇到流中带 `error` 键的数据包会抛 `APIError`（主会话已读 `openai/_streaming.py`）；生产 OOM 的消息就含这两个串（window01 `ladder.jsonl`，独审已核实）。
- 请求抛出任何异常后立即读 `/health`：连接失败、`status != "ok"`、`maintenance != "serving"`，或 `backend_epoch != backend_epoch_0`。
- C2 或 C3 看到 `maintenance != "serving"` 或 `backend_epoch` 变化。

请求出错但以上都不满足时，判为 `error`，运行立即停止（§3.2.8）。

**判为 `oom` 后，一律停止运行**：

1. 等本事件所有线程结束，最多 60 s。
2. 每 5 s 读一次 `/health`（连接失败算"未恢复"），直到 `status=="ok"` 且 `maintenance=="serving"`，最多 360 s。记录恢复用时、新的 `backend_epoch` 与 `restart_attempts`，以及恢复后 `/v1/stats` 的 `active`（预计 > 0）。
3. 从生产日志（`production.active.json` 的 `log` 字段）**只读**截取含 `out of memory`、`OutOfMemory`、`worker_restarting` 的行，前后各 40 行，存为 `<out>/oom_1_serve_excerpt.log`。
4. 写 `<out>/oom_1.json`：事件标签、时刻、错误消息、事件前后显存、恢复用时、epoch 前后值、恢复后的 `active`。
5. 分类：
   - 360 s 内恢复 → `terminal=oom_stop`；
   - 未恢复 → `terminal=production_not_recovered`。

**你在协调日志里要写的告警**（工装停止后立刻写）：

- `oom_stop`：
  > **告警：D11-P0 在 `<事件标签>`（`<时刻>`）触发 481 OOM，已自动恢复（epoch `<n>`）。481 本进程的自动恢复额度已用完，再 OOM 将停服直到人工重启；`/v1/stats` 的 active 已失真（= `<n>`）。**
- `production_not_recovered`：
  > **P0 告警：481 OOM 后 360 s 未恢复**（附 `/health` 原文）。

  不要对服务做任何操作，等主会话处理。

**对生产的影响**（要写进报告）：

- OOM 期间约 4 min，局域网用户不可用。
- 生产观察器（`observe_overnight.py`，只读，每 60 s 采样一次）会记录到 `backend_epoch ≠ 0`，今晚的观察结论会变为 `requires_review`，明早的推送资格要由主会话人工复核。
- 在 481 下一次重启之前，它都没有自动恢复余量。D09 窗口的 restore11 会让额度复位，这也是 §2.1 建议先测 D11-P0 的原因。

#### 3.2.6 计划

**`--plan smoke_then_full`**（生产与演练都用这一个入口，共 26 个事件）：

| 序号 | 标签 | 内容 | A max_tokens | B |
|---|---|---|---|---|
| 0 | `smoke` | 只有 A | 96 | — |
| — | — | **smoke 门**：事件状态为 ok，`a_tps` ≥ 20，C3 的 `completed` 差值为 1。任一不满足 → 停止，`terminal=smoke_failed` | — | — |
| 1–2 | `solo-a1`、`solo-a2` | 只有 A | 384 | — |
| 3 | `W-L64` | 只有 B（L64，预热，不计成绩） | — | max_tokens 16 |
| 4 | `W-L80` | 只有 B（L80，预热，不计成绩） | — | 16 |
| 5–11 | `t1-r00` … `t1-r06` | A + B 配对；r00 为冷事件，r01–r06 为热事件 | r00 用 1,536，其余 384 | 16 |
| 12–18 | `t2-r00` … `t2-r06` | 同上 | 同上 | 16 |
| 19–25 | `t3-r00` … `t3-r06` | 同上 | 同上 | 16 |

另提供 `--precheck-only`（只做 §3.2.9 的前置检查，不发任何生成请求），供 R6 使用。

**时间预算**（主会话推算）：

| 部分 | 估算 |
|---|---|
| smoke 与 A 单独 2 次 | 约 35 s |
| 预热 2 次 | 约 35 s |
| 每条配对轨迹 | 冷事件约 70 s（A 1,536 token）；热事件 6 × 约 19 s（B 两段预填约 6 s，加上 A 剩余的输出）；合计约 185 s。3 条约 9.3 min |
| 事件间隔与空闲检查 | 约 1.5 min |
| **合计** | **约 12 min** |

**时间上限**：从运行开始算 30 min。每个事件开始前检查：已超过 30 min 就停止；剩余不足 4 min 时，不再开始新轨迹。已经开始的事件跑完再停。两种情况都记为 `time_limit`。

#### 3.2.7 每个事件的指标

记 A 的有效分片到达时刻为 t₁, t₂, …；B 的首个有效分片时刻为 `t_Bfirst`。

| 指标 | 定义 | 适用 |
|---|---|---|
| `a_base_itl_ms` | 第 16 至第 64 个有效分片之间 48 个间隔的中位数 | 配对、只有 A |
| `b_ttft_ms` | `t_Bfirst − t_Bsend` | 有 B 的事件 |
| 停顿窗口 W | 所有相邻对 (tᵢ, tᵢ₊₁)，满足 tᵢ₊₁ > `t_Bsend` 且 tᵢ < `t_Bfirst` + 1,000 ms | 配对 |
| `a_max_gap_ms` | W 中间隔的最大值；同时记录该对相对 `t_Bsend` 的起止时刻 | 配对 |
| `stall_ms` | `a_max_gap_ms − a_base_itl_ms` | 配对 |
| `a_gaps_over_3x` | W 中大于 3 × `a_base_itl_ms` 的间隔个数 | 配对 |
| `a_extra_ms_sum` | W 中所有大于 3 × `a_base_itl_ms` 的间隔，各自减去 `a_base_itl_ms` 后求和。停顿被拆成几段时，这个值会明显大于 `stall_ms` | 配对 |
| `a_interf_tps` | (`t_Bsend`, `t_Bfirst`] 内 A 收到的有效分片数 ÷ `b_ttft_ms` | 配对 |
| `a_streaming_after` | A 在 `t_Bfirst` + 1,000 ms 之后仍有有效分片；否则事件记为 `a_finished_early` | 配对 |
| `a_tps` | (有效分片数 − 1) ÷ (末片时刻 − 首片时刻) | 只有 A |
| `a_natural_max_gap_ms` | 第 16 个有效分片之后相邻间隔的最大值（自然状态下的偶发卡顿） | 只有 A |
| usage | 各请求的 `prompt_tokens`、`completion_tokens`、`cached`；`b_uncached = prompt_tokens − cached` | 全部 |
| `b_server_ttft_ms` | C4 中 B 那条请求环记录的 `ttft_ms`（诊断用） | 有 B 的事件 |
| `b_prefill_lines` | **运行结束后**只读解析生产日志：取时间戳落在 [事件开始 − 1 s, 事件结束 + 1 s] 内的 `Prefill batch` 行（日志时间为本地时间，精度 1 s），提取 `#new-token` 与 `#cached-token`。A 的预填行 (27, 1152) 或 (1179, 0) 排除，其余归 B。记录原文与行数 `b_prefill_segments` | 有 B 的事件 |
| `gpu_mem_mib` 前/后 | `nvidia-smi --query-gpu=memory.used` | 冷事件、预热事件 |
| `loadavg_1m` | 事件开始时的 `os.getloadavg()[0]` | 全部 |

#### 3.2.8 停止规则与失败去向（都不重试）

| 情况 | 本事件记为 | 运行 | `terminal.json` 分类 |
|---|---|---|---|
| 运行前前置检查不通过 | — | 不开始 | `precondition_failed` |
| smoke 门不通过 | 按实际 | 停止 | `smoke_failed` |
| STOP 文件出现（每个事件前检查） | — | 停止 | `vetoed` |
| 审批号或 GPU 锁 owner 变了（每个事件前检查） | — | 停止 | `production_changed` |
| C1 等待 120 s 仍不空闲 | — | 停止 | `production_busy` |
| 累计 `contaminated` ≥ 3 | `contaminated` | 停止 | `production_busy` |
| 非 OOM 的请求错误或超时 | `error` | 立即停止 | `error` |
| OOM，360 s 内恢复 | `oom` | 停止 | `oom_stop` |
| OOM，360 s 内未恢复 | `oom` | 停止，写 P0 告警 | `production_not_recovered` |
| 超时（§3.2.6） | — | 停止 | `time_limit` |
| B 无有效分片 | `b_empty` | 继续 | — |
| A 提前结束 | `a_finished_early` | 继续 | — |
| 全部跑完 | — | — | `complete` |

#### 3.2.9 运行前的前置检查

**生产模式**（`--endpoint` 不是 127.0.0.1）：

1. 用子进程运行 `WORK/d11p0_precheck.py`。它是附件 `plan/GEMINI_D11_P0_PRECHECK_20261011.py` 的字节副本，运行前先核对 SHA256 为 `9e2d94577d5eda3bb383d46e08f7ff3a986b458b0bc80cc68e0bda15ceeae2ac`。
2. 解析它输出的 JSON，退出码必须为 0。这样工装用的就是主会话预演过的同一套 10 道门：
   - 审批号（-10 或 -11）与提交；
   - serving；
   - 自动恢复额度完好（`backend_epoch == 0` 且 `restart_attempts == 0`）；
   - 当前空闲；
   - 唯一的 `ft serve` 就是生产 service pid；
   - 没有其他 `stall_probe.py`（附件已排除自身及所有祖先进程）；
   - 没有 D09 窗口进程；
   - GPU 锁属于生产；
   - 没有 STOP 文件；
   - ollama 未运行。
3. 另外再查两条：
   - `WORK/REHEARSAL.json` 中 R1–R6 全部 PASS，且其中记录的 `stall_probe.py` 的 SHA256 与当前文件一致；
   - `--out` 目录事先不存在（`mkdir(exist_ok=False)`）。

**演练模式**（`--endpoint http://127.0.0.1:...`）不运行附件，因为它查的是生产。改由工装自己检查：

- STOP 文件；
- 桩服务 `/health` 为 serving；
- 桩服务 `/v1/stats` 的 `active == 0`；
- `--out` 目录不存在。

STOP 文件路径可以用 `--stop-file` 改为临时路径，默认即生产路径。

#### 3.2.10 输出（`--out` 目录）

| 文件 | 内容 |
|---|---|
| `precheck.json` | 前置检查结果（生产模式下就是附件输出的原文） |
| `events.jsonl` | 每个事件一行：标签、状态、全部指标、A 与 B 的原始有效分片时间序列（相对事件开始的毫秒数）、usage、C2 全部样本、C3 与 C4 的结果、显存 |
| `prefill_lines.json` | 运行结束后解析的 `b_prefill_lines` |
| `summary.json` | 按 §5 口径分组的统计：中位数、最小值、最大值、计数 |
| `terminal.json` | 分类、开始与结束时刻、执行与跳过的事件数、`contaminated` 数、OOM 信息、错误 |
| `oom_1.json`、`oom_1_serve_excerpt.log` | 只在发生 OOM 时 |

每个文件用 `x` 模式新建，写完设为 0444。

### P1-3 `stub_server.py`：桩服务（只用于演练）

只用标准库 `http.server.ThreadingHTTPServer`，监听 `127.0.0.1:18300`；被占用就依次试 18301–18309，并记录实际端口。行为尽量与生产一致。

**接口**

- `GET /health`：`{"status":"ok"|"error","maintenance":"serving"|"restarting","backend_epoch":n,"restart_attempts":n}`。
- `GET /v1/stats`：至少包含 `requests.active`、`requests.completed`，以及 `recovery.maintenance`、`recovery.backend_epoch`。`active` 的增减时机与生产一致：收到请求即加入；发送结束包之前移出，正常结束时 `completed` 加 1。
- `GET /v1/requests?since=&limit=`：语义与 `server/request_ring.py` 相同，容量 512。每个聊天请求**结束时**记 1 条：`path=/v1/chat/completions`，带真实的 `duration_ms`、`ttft_ms`、`prompt_tokens`、`completion_tokens`。
- `GET /v1/models`。
- `POST /v1/chat/completions`（只支持流式），依次发送：
  1. **立即**发 role 包 `{"delta":{"role":"assistant","content":""}}`；
  2. 按"引擎模拟"逐 token 发 `reasoning_content` 分片，正好 `max_tokens` 个；
  3. 结束包（`delta:{}`，`finish_reason:"length"`）；
  4. usage 包（`choices:[]`；cached 为 0 时不带 `prompt_tokens_details`，与生产一致）；
  5. `data: [DONE]`。

**引擎模拟**：全局一个"预填锁"。新请求到达时，先持锁 D 秒（模拟预填），其间所有正在输出的请求暂停；释放后，各请求按 `--itl` 的间隔继续输出。

| 请求类型 | D |
|---|---|
| 带 tools、只有 1 条消息、内容超过 100,000 字符（冷事件、预热） | `--d-cold` |
| 带 tools 的其他请求（热事件） | `--d-warm` |
| 不带 tools 的请求（A） | 0.05 s |

**usage 规则**（让 §5 的缓存检查在演练中也走真实逻辑）：

| 请求 | prompt_tokens | cached |
|---|---|---|
| round-k（带 tools，按消息条数 2k+1 识别） | 录制 P_k + 16 | k=0 时为 0；否则 floor((P_{k−1} + 16) / 64) × 64 |
| 预热 L64 / L80 | 64,000 + 16 / 80,000 + 16 | 0 |
| A | 1,179 | 第一次为 0，之后为 1,152 |

**注入**（命令行传 JSON）：

- `--inject '[{"kind":"complete"|"abort","start_on_b":n,"delay_s":x,"duration_s":y}, ...]'`
  - `start_on_b`：第 n 个**带 tools 的请求**。L64、L80 和各轮 B 都带 tools，A 不带。
  - 在该请求到达后 x 秒，加入一个外来在途请求，持续 y 秒。
  - `complete`：结束时 `completed` 加 1，写一条请求环记录。
  - `abort`：结束时只从在途集合移除，`completed` 不加，写一条 `error="aborted"`、`prompt_tokens=0` 的请求环记录。
- `--oom-on-marker '<子串>'`：单条消息、且 `messages[0].content` 含该子串的请求到达 1.0 s 后：
  - 向所有在途流发送 `data: {"error":{"message":"worker_restarting_after_oom: OutOfMemoryError: CUDA out of memory (stub)","type":"server_error"}}` 并关闭；
  - **这些流不从 `active` 中移出**（模拟生产 `fail_dispatched_for_oom` 的行为）；
  - 进入 `restarting`，持续 `--oom-recover-s` 秒（默认 10），期间新的聊天请求返回 HTTP 503；
  - 之后 `backend_epoch` 与 `restart_attempts` 各加 1，回到 `serving`。

### P1-4 `test_stall_probe.py`：单元测试

至少覆盖以下各项，每项都要有断言：

1. **有效分片**：
   - role 包（`content=""`）、结束包、usage 包都不计；
   - `content`、`reasoning_content`、`tool_calls` 各自非空时计 1；
   - 构造一条"把 role 包算进去会得到 `b_ttft_ms` < 100"的时间序列，断言工装算出的是正确值；
   - B 无有效分片 → `b_empty`。
2. **指标**：在合成时间序列上验证：
   - `a_base_itl_ms`；
   - 停顿窗口 W 的两个边界：跨 `t_Bsend` 的那一对要计入；起点晚于 `t_Bfirst` + 1 s 的要排除；
   - `stall_ms`、`a_extra_ms_sum`、`a_gaps_over_3x`：用一条"两段停顿中间夹一个分片"的序列；
   - `a_interf_tps`、`a_finished_early`。
3. **usage**：`prompt_tokens_details` 为 `None` 时 `cached = 0`。
4. **防混入**：
   - C2 的区间相交规则，含 0.2 s 余量的边界；
   - C3 的 `completed` 差值多 1、少 1；
   - C4 的多重集不一致：条数相同但 `prompt_tokens` 不同。
5. **OOM 分类**：按消息特征；按 `status`/`maintenance`；按 epoch；普通错误判为 `error`。OOM 后一律停止；恢复与未恢复两种分类都要有。
6. **停止规则**：`contaminated` 第 3 次时停；时间上限；STOP 文件；`production_changed`；smoke 门。
7. **KV 断言**：构造一个超过 98,304 的事件，必须拒绝；真实计划必须通过。
8. **计划**：标签顺序与 §3.2.6 一致；同一轨迹 7 轮的标记相同，不同轨迹不同。
9. **客户端构造**：SDK 客户端 `max_retries == 0`；httpx 客户端 `trust_env` 为 False；urllib opener 不含代理。
10. **日志解析**：给定一段含 A、B 两类 `Prefill batch` 行的合成日志，正确排除 A 的行，并按时间窗归属到事件。

运行：`cd WORK && $PY -m pytest -q -p no:cacheprovider test_stall_probe.py`，必须全部通过。

### P1-5 真实入口演练（交付 `WORK/REHEARSAL.json`，0444）

R1–R5 都用 `stall_probe.py --plan smoke_then_full` 的真实代码路径，只把 `--endpoint` 换成桩服务地址，`--out` 用 `RUNS/rehearsal/<名称>`。每项开始前新起一个桩服务，结束后关掉。

| 演练 | 配置 | 必须得到的结果 |
|---|---|---|
| **R1 正向对照** | `--itl 0.034 --d-cold 3.0 --d-warm 1.0` | • 26 个事件全部为 ok；<br>• 冷配对事件 `stall_ms` 在 2,700–3,300；<br>• 热配对事件 `stall_ms` 在 900–1,100；<br>• 预热事件 `b_ttft_ms` 在 2,900–3,300；<br>• `terminal=complete`；<br>• §5.3 的 G1–G4 全部通过；全部热事件的缓存检查通过 |
| **R2a 反向：短外来请求** | `--itl 0.005 --d-cold 0.3 --d-warm 0.1`；注入 `complete`，`start_on_b=4, delay_s=0.05, duration_s=0.2`（第 4 个带 tools 的请求是 `t1-r01`） | 恰好 1 个事件为 `contaminated`，就是 `t1-r01`；运行跑完，`terminal=complete` |
| **R2b 反向：连续 3 次** | 同上速度；注入 3 个 `complete`，`start_on_b` 依次为 5、6、7，`delay_s=0.05, duration_s=0.2` | `t1-r02`、`t1-r03`、`t1-r04` 为 `contaminated`；在 `t1-r04` 之后停止，`terminal=production_busy`；共执行 10 个事件（smoke、solo×2、W×2、t1-r00…r04） |
| **R2c 反向：中途中止** | 同上速度；注入 `abort`，`start_on_b=4, delay_s=0.05, duration_s=1.0` | 恰好 `t1-r01` 为 `contaminated`，并在 `events.jsonl` 中写明是被 C2 还是 C4 抓到的；运行跑完 |
| **R3 无停顿对照** | `--itl 0.034 --d-cold 0 --d-warm 0` | 全部配对事件 `stall_ms` < 200；运行跑完。§5.3 的 G2 **必须判为不通过**（没有预填，冷热首字时间没有差别），以此证明 G2 能抓住"预填没有发生" |
| **R4 OOM** | `--itl 0.005 --d-cold 0.3 --d-warm 0.1 --oom-on-marker "traj=t1]" --oom-recover-s 10` | • 事件依次为 smoke、solo×2、W×2、`t1-r00`=oom，之后停止，共执行 6 个事件；<br>• `terminal=oom_stop`；恢复用时 8–20 s；<br>• `oom_1.json` 中 epoch 为 0→1，恢复后 `active` 记为 2（桩服务模拟的泄漏）；<br>• 摘录生产日志的那一步在演练模式下改读桩服务日志，或记为"演练跳过"，并写进 REHEARSAL.json |
| **R5 前置门反向** | `--plan smoke_then_full --stop-file <临时路径>`，事先创建这个临时文件 | 拒绝运行，`terminal=precondition_failed`，原因写明 STOP 文件；随后删除临时文件 |
| **R6 生产前置检查路径** | `stall_probe.py --endpoint http://172.16.108.9:8095 --precheck-only --out RUNS/rehearsal/R6`。只读，不发生成请求 | • 附件子进程已运行，JSON 解析成功；<br>• `gates.no_other_probe == true`，证明父进程 `stall_probe.py` 没被算成另一个 probe；<br>• 前后两次读 `/v1/stats`，`completed` 没有因本次运行而增加；<br>• 其余各门照实记录。若 R6 时 D09 窗口正在进行，`approval`、`serving` 等门不通过是正常的，R6 仍可判 PASS，因为它检验的是路径 |

`REHEARSAL.json` 内容：

- 每项的配置、期望、实际，以及 PASS/FAIL；
- `stall_probe.py`、`stub_server.py`、`freeze_inputs.py`、`test_stall_probe.py`、`d11p0_precheck.py`、`INPUTS.json` 与 `inputs/` 下全部文件的 SHA256。

**写完之后，这些文件一律不得再改**；改了就要重做 R1–R6。

### P1-6 CPU 就绪（交付 `WORK/CPU_READINESS.md`，0444）

内容：

1. 文件清单与 SHA256；
2. pytest 输出原文；
3. R1–R6 结果表；
4. P1-1 各条断言的实际输出，包括录制值表与 KV 表；
5. `WORK/d11p0_precheck.py` 的 SHA256，必须为 `9e2d9457…`（全长见 §3.2.9）。

另外两件事：

- 在 `LOCAL/README.md` 末尾追加一节"D11-P0 停顿基线工装（2026-10-11）"，写明入口、目录，以及"只发请求、不动服务"（工作区 AGENTS.md 第 3.3 条的要求）。
- 协调日志写"D11-P0 CPU 就绪"，附 REHEARSAL.json 与 stall_probe.py 的 SHA 前 12 位。

---

## 4. P2：生产测量（主会话预授权；条件满足即执行，不必等回复）

### 4.1 放行条件（全部满足才开始）

1. P1-6 已完成，R1–R6 全部 PASS。
2. 符合 §2.1 的先后规则：没有 D09 窗口在进行。
3. `ssh 9 'cd /data2/FreeToken/development/gemini_d11_p0_20261011 && /data2/FreeToken/evaluation/toolchain/venv-eval/bin/python d11p0_precheck.py'` 的退出码为 0，即 10 道门全过。主会话 19:31 在副本上原样跑过：全部为 true，退出码 0。
   - 如果只有 `idle_now` 不通过（有人在用），每 5 min 重跑一次，最多等 60 min。60 min 后仍忙，就在协调日志写"**D11-P0 今日不测（生产忙）**"并结束。
   - 如果 `restart_budget_intact` 不通过（之前已经 OOM 过），**不测**：在协调日志写明 `/health` 原文，等主会话。
4. 本地 `LOCAL/plan/GEMINI_D11_P0_STOP.md` 与服务器 `SRV/plan/GEMINI_D11_P0_STOP.md` 都不存在。附件只查服务器侧，本地侧由你在办公电脑上查。

### 4.2 执行（一次启动，smoke 与 full 在同一进程内）

客户端在 9 号机本机运行，用 `setsid nohup` 脱离 ssh 会话，避免断线把测量杀掉：

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_d11_p0_20261011 && PY=/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python && mkdir -p /data2/FreeToken/runs/dev_gemini_d11_p0_20261011 && setsid nohup $PY stall_probe.py --endpoint http://172.16.108.9:8095 --plan smoke_then_full --out /data2/FreeToken/runs/dev_gemini_d11_p0_20261011/run01 > /data2/FreeToken/runs/dev_gemini_d11_p0_20261011/run01.log 2>&1 < /dev/null &'
```

运行期间每 1–2 min 看一次进度：

```bash
ssh 9 'tail -c 600 /data2/FreeToken/runs/dev_gemini_d11_p0_20261011/run01.log; ls /data2/FreeToken/runs/dev_gemini_d11_p0_20261011/run01'
```

`run01/terminal.json` 出现即结束。期间不要在服务器上做别的事（红线 8）。

### 4.3 失败去向

| 步骤 | 失败 | 去向 |
|---|---|---|
| 放行条件 1 | 演练有 FAIL | 不测。修代码后**重做全部 R1–R6**，不能只重做失败项 |
| 放行条件 2 | D09 窗口在进行 | 等它结束、-11 恢复后再查（§2.1） |
| 放行条件 3 | 除 `idle_now` 外任一门不通过 | 不测。协调日志写明哪道门、实际值，等主会话 |
| 放行条件 3 | 等满 60 min 仍忙 | "D11-P0 今日不测（生产忙）"，结束 |
| 运行中 | 见 §3.2.8 | 按分类写报告；`oom_stop` 与 `production_not_recovered` 先按 §3.2.5 写告警 |
| 任何时候 | 发现 481 不再 serving，且不是你的事件引起的 | 立即停止测量，协调日志写明时刻与 `/health` 原文，不碰服务 |

---

## 5. P3：结果报告与预登记读法

### 5.1 报告

写在 `WORK/RESULT.md`（0444），并同步到本地镜像。内容：

1. 每一步的终态与时刻（前置检查、smoke、full）。
2. **事件总表**：标签、状态、`b_uncached`（及与录制值 U 的差）、`b_ttft_ms`、`b_server_ttft_ms`、`b_prefill_segments`、`stall_ms`、`a_gaps_over_3x`、`a_extra_ms_sum`、`a_interf_tps`、`a_base_itl_ms`。
3. 按轮（r01…r06）汇总 t1–t3 的停顿（中位数、最小值、最大值），并列出该轮的 U 与 B 的预填段数。
4. §5.3 的 G1–G4 与 F1–F3。
5. `G_warm`、`G_warm_sum`、`G_cold`，以及按 §5.5 应给出的档位（只写档位，不写立项建议）。
6. 被排除的事件及原因。
7. 若有 OOM：时刻、事件、恢复用时、epoch 变化、恢复后的 `active`，以及"对生产与观察器的影响"一节。
8. 证据 SHA256 索引。
9. 必须写明：A 路是模板文本（21 行中只有 12 行不同），只用来保持解码；停顿大小由 B 的真实内容决定。另须写明：本测量是**不开 D09** 时的基线，热轮的预填是两段。

没有数据直接支持的解释一律标为"推测"。

### 5.2 单个配对事件何时有效

以下全部满足才算有效：

- **状态为 ok**：不是 `contaminated`、`oom`、`error`、`a_finished_early`、`b_empty`。
- **缓存检查**：
  - 冷事件 `cached` ≤ 640。tools 段的锚点快照可能正好落在 512，独审在 `G_seed_45k` 的日志里见过 `anchor_cap reqs=0:512/0`；
  - 热事件 |`b_uncached` − U_k| ≤ 128。主会话推算偏差 ≤ 64：标记行让每一轮都多出同样的 δ 个 token，64 对齐的命中位置最多因此移动一档。
- **物理上界**：`stall_ms` ≤ `b_ttft_ms` + 500。A 的最长间隔不可能比 B 的首字时间多出一个解码步以上；超出就说明这段停顿另有原因。

### 5.3 合理性检查

**G 类**：任一项不通过，整个结果记为"**异常、待诊断**"，不给 §5.5 的档位。

| 编号 | 检查 | 预期 |
|---|---|---|
| G1 | 两次 A 单独事件的 `a_tps` 都 ≥ 20 | 约 29.7 |
| G2 | 冷配对事件 `b_ttft_ms` 的中位数 > 2 × 热配对事件 `b_ttft_ms` 的中位数 | 约 3 倍（§1.2） |
| G3 | 热事件中缓存检查不通过的 ≤ 3 个 | 0 |
| G4 | 违反物理上界的事件 ≤ 1 个 | 0 |

**F 类**：只做标记，照常给出档位。

| 编号 | 标记条件 | 含义与报告要求 |
|---|---|---|
| F1 | `G_warm` ÷ 热配对事件 `b_ttft_ms` 的中位数 < 0.5 | 停顿明显短于 B 的首字时间。多半是两段预填之间插入了 A 的解码。须对照 `a_gaps_over_3x`、`b_prefill_segments` 与 `G_warm_sum` 说明 |
| F2 | 任一事件开始时 `loadavg_1m` > 8 | CPU 有干扰 |
| F3 | 同一轮在 t1–t3 之间停顿的最大值 ÷ 最小值 > 2 | 重复性差 |

### 5.4 G_warm、G_warm_sum 与 G_cold

| 量 | 定义 | 完整性 |
|---|---|---|
| `G_warm`（主） | 有效热配对事件（t1–t3 的 r01–r06，最多 18 个）`stall_ms` 的中位数 | 有效事件 ≥ 12 个为"完整"；6–11 个为"部分"，照常给档位，但须注明；< 6 个为"不足"，不给档位 |
| `G_warm_sum`（辅） | 同一批事件 `a_extra_ms_sum` 的中位数 | 同上 |
| `G_cold` | 有效冷配对事件（最多 3 个）`stall_ms` 的中位数 | ≥ 2 个才报 |

同时报告：预热事件的 `b_ttft_ms` 与显存变化。

### 5.5 D11 价值档位（预登记，测完不改）

档位按 `G_warm`（主）判定：

| `G_warm` | 档位 |
|---|---|
| < 1.0 s | 不建议立项：热轮次停顿不到 1 s；冷启动只在会话开始时发生一次 |
| 1.0–2.0 s | 两组数字都报，交用户决定 |
| ≥ 2.0 s | 停顿真实存在且明显。主会话据此重算 D11 的理想停顿（一段预填时间 ÷ (k+1)）和对 B 首字时间的代价，交用户决定是否批准 15–25 人日 |

补充规则：

- 若 `G_warm` < 2.0 s 而 `G_warm_sum` ≥ 2.0 s（停顿被切成多段），报告写"停顿被切成多段"，两组数字一并交用户。
- 主会话复核时还会另算一项：按 D09 启用后热轮只剩一段，估计那时的停顿。这样 D11 与 D09 的收益不会重复计算。

---

## 6. 复盘与自检（主会话下发前完成）

### 6.1 主会话自查

| # | 项 | 核对结果（附数字或证据） |
|---|---|---|
| 1 | D11-P0 是否已经测过 | **没有**。服务器上没有 `development/d11_p0_stall_20261011/`，没有 `runs/dev_d11_p0_20261011/`，也没有 `stall_probe` 进程；协调日志里 Codex 在 11:41 之后没有任何 D11-P0 记录。18:42 的复核（`plan/GEMINI_OOM_HYBRID_REVIEW_20261011.md` §1）结论相同 |
| 2 | 负载内容（检查内容本身） | 逐条读取：<br>• X0 有 6,356 字符，21 行中只有 12 行不同，是模板文本，SHA 正确；<br>• round-00 只有 1 条 user 消息，345,089 字符，带 3 个 tools；<br>• round-01…06 的 `messages[0]`、tools 都与 round-00 完全相同，消息条数为 3–13；<br>• 7 轮的录制 usage 见 P1-1 的表 |
| 3 | 缓存命中前提 | 7 轮的 `cached` 全部等于 floor(上一轮 P / 64) × 64；481 上 X 的热请求命中 1,152 / 1,179，也符合这一规律。录制引擎与 481 的 `special_token_ckpt`、`prefill_anchor_cut`、`prefill_layer_major`、radix 缓存设置相同 |
| 4 | KV 容量 | 冷事件 89,895，最大的热事件 94,912，都 ≤ 98,304 |
| 5 | 分片定义 | 读录制 SSE 原文：首包 `{"role":"assistant","content":""}` 的 created 比首个 token 早 19 s；在 venv-eval 中核实 SDK 解析后 `content == ''` |
| 6 | 防混入 | 读码：`request_ring.py`、`api_server.py:255-300,495-545`、`generation.py:508-596`、`stats.py`、`control_api.py:70-74`。今晚冒烟的 `duration_ms` 为 3 和 5，证实回溯法会漏。R2a、R2b、R2c 分别覆盖"完成、连续、中止"三种外来请求 |
| 7 | 代理、重试、错误包 | 预演时 urllib 报 `unknown url type: socks5`，改用 `ProxyHandler({})` 后通过；`httpx.Client(trust_env=False)` 列模型成功。SDK `max_retries` 默认值为 2；流中有 `error` 键时 SDK 抛 `APIError`（已读 `_streaming.py`） |
| 8 | OOM 风险与额度 | 87K 级冷请求 4 例中 2 例 OOM；481 每个进程只有 1 次自动恢复额度（`api_server.py:1234`，已读原文）。处置：首次 OOM 即停；前置检查要求额度完好；建议在 D09 窗口之前测；冷预填由 4 次减到 3 次。最坏情况：约 4 min 中断，之后 481 在下次重启前没有恢复余量，观察器结论变为 `requires_review`。会在回复中告知用户 |
| 9 | 观察器 | `observe_overnight.py` 共 51 行，已读全文：只读，`generation_requests: 0`，每 60 s 采样一次，不发请求。18:25 到 19:31 之间，请求环里只有冒烟的 2 条 |
| 10 | 与 Codex、D09 的冲突 | Codex 未开始，19:01 已放 STOP 文件（`18b2c77d…`）。另一主会话 19:10 发的 Codex 补充 2 早于本指令，但 STOP 文件仍按 Codex 原指令第 4 节第 5 条生效。D09 的 W0 会避让 `stall_probe.py` 进程；本指令改为一次启动，并在前置检查中核对 D09 进程与 GPU 锁 |
| 11 | 命令先在副本上跑 | 附件 v2（`9e2d9457…`）19:31 在服务器上原样运行：10 道门全部 true，退出码 0。另做了两项对照：<br>• 正向：从名为 `stall_probe.py` 的父进程里用子进程调用，`no_other_probe=true`；<br>• 反向：另起一个不相关的 `stall_probe.py`，被抓到（pid 2802967），`all_pass=false`，测试进程已清理 |
| 12 | 判据与执行设置逐条对照 | • G1 ≥ 20，预期 29.7；<br>• G2 > 2 倍，预期约 3 倍；R3 证明 G2 能抓住"没有预填"；<br>• 热事件 ±128，推算偏差 ≤ 64；冷事件 ≤ 640；<br>• 时间上限 30 min，预计 12 min；<br>• R2b 期望第 3 个 `contaminated` 时停止，与 §3.2.8 一致；R4 期望首次 OOM 即停，与 §3.2.5 一致；<br>• 冷事件 A 用 1,536 token：即使引擎在预填中穿插解码，18.6 s × 30 tok/s ≈ 560 个，仍有余量，另有 `a_finished_early` 兜底 |
| 13 | 失败去向逐步推导 | §3.2.8（运行中）与 §4.3（运行外）两张表。删去 t0、改为首次 OOM 即停、改为一次启动之后，R1–R6 的事件序列与事件数已按新顺序重写（R1 26 个、R2b 10 个、R4 6 个） |
| 14 | 每段等待凭什么 | 没有钟点等待。只有两种等待：(a) 生产忙，依据是防混入，上限 60 min；(b) D09 窗口进行中，依据是不能交错 |
| 15 | 关键路径上的人工环节 | 没有。放行全部是机械检查；主会话否决用 STOP 文件 |
| 16 | 推算值标注 | §1.2 全部标为推算。热轮"两段之间是否插入解码"写成两种可能，由 `a_gaps_over_3x` 与日志段数回答 |
| 17 | 等价判据的对照臂 | 不适用：本测量不含"相等/可复现"判据 |
| 18 | 环境一致性 | ollama（bge-m3）容器仍停止；`ollama_pre_opt_…` 容器 CPU 0.0%，与 window01、window02 时相同 |

### 6.2 独立审核（critic）的发现与处置

| 级别 | 发现 | 主会话核实 | 处置 |
|---|---|---|---|
| CRITICAL | 第 2 次 OOM 后 481 停在 failed，不会自动恢复；初稿写的"最坏中断 2 × 4 min"不成立 | 读 `api_server.py:1187-1199,1234`、`supervisor.py:209-235`、`control_api.py:27-28`，成立 | 首次 OOM 即停；新增"自动恢复额度完好"门；如实写出影响；R4 改为首次 OOM 即停 |
| HIGH | 工装用子进程调用前置检查时，父进程 `stall_probe.py` 会让检查判自己不通过 | 逻辑成立；附件 v2 已用正、反两项对照验证 | 附件改为排除自身及所有祖先进程；新增 R6 走生产路径 |
| HIGH | OOM 后 `active` 永久多算 | 读 `api_server.py:364-379`，成立 | 首次 OOM 即停；记录恢复后的 `active`；桩服务模拟这一泄漏 |
| MEDIUM | 热轮预填是两段，各约 2.7 s；B 分词期间 A 的输出会积压 | 读录制 `serve.log` 第 44–49 行，成立 | 重写 §1.2 的预测；G2 预期改为 3 倍；新增 `G_warm_sum` 与 `b_prefill_lines`；F1 改写解释 |
| MEDIUM | 与 D09 窗口的先后没写；附件只认 -10，日志路径写死 | 读 D09 指令与 Codex 补充 2，成立 | 新增 §2.1；认 -10 和 -11；日志路径从 `active.json` 读；改为一次启动 |
| LOW | 注入规则中的"B 类请求"未定义 | 成立 | 改为"带 tools 的请求" |
| LOW | 初稿引用了不存在的"§4.1 第 7 条" | 成立 | 已改为第 4 条 |
| LOW | R4 恢复用时上限 15 s 太紧 | 成立（每 5 s 轮询一次） | 改为 8–20 s |
| LOW | 冷事件 `cached ≤ 512` 没有余量 | 成立 | 放宽到 ≤ 640 |
| LOW | B 无有效分片时 `t_Bfirst` 未定义 | 成立 | 新增 `b_empty` |

---

## 7. 纪律

- 只追加、不覆盖；每一步在协调日志写一行，时间戳为真实的写入时刻。
- 拿不准就停，写明原因，等主会话。
- 测量结束后，协调日志必须写一行"**D11-P0 测量完成**"，附 `terminal.json` 的分类与 RESULT.md 的 SHA 前 12 位；决定不测时写"**D11-P0 今日不测**"，并附原因。

## 附件

- `plan/GEMINI_D11_P0_PRECHECK_20261011.py`（SHA256 `9e2d94577d5eda3bb383d46e08f7ff3a986b458b0bc80cc68e0bda15ceeae2ac`，本地与服务器一致，0444）：只读前置检查，输出一个 JSON，退出码 0 表示 10 道门全过，3 表示有门不过。
