# Gemini 指令：OOM 显存诊断 + 可复现 hybrid 验证（2026-10-11，主会话）

> 读者是第一次接手本项目的执行者，下文对环境、约定和每一步都写全了。请**从头到尾读完再动手**。遇到本文没写到的情况，就停下来，在协调日志里写明原因，等主会话处理。**本文件发出后冻结，不再修改**：restore10 的独审字段绑定本文件的 SHA256；如需更正，主会话会另发补充文件。

---

## 0. 你的角色、环境与红线

### 0.1 角色

- **你**：执行者。负责编写测试工装、在 CPU 上演练、执行 GPU 窗口、写报告。
- **主会话**：审核者。负责写指令、复核结果。
- **用户**：拍板人。

本指令已经得到用户批准（2026-10-11 下午）：

- hybrid 定为"可选模式"，继续优化，并测一版"可复现 hybrid"；
- 生产配置 87K 请求的 OOM，立即做诊断。

### 0.2 环境

| 项 | 值 |
|---|---|
| 测试服务器 | `172.16.108.9`。从办公电脑用 `ssh 9 '<命令>'` 执行，登录用户 dell |
| 本地仓库 | `D:\00.开发\2026\03-模型实验\freetoken\freetoken\`（下称 LOCAL）。服务器对应目录 `/data2/FreeToken/`（下称 SRV） |
| Python 环境 | 引擎与工装 `/data2/FreeToken/venv/bin/python`；OpenAI SDK 客户端 `/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python`（openai 2.54.0、pytest 9.1.1）；AIPerf `/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf` |
| 发布版代码（只读） | `SRV/wt/release-e2/python/freetoken/`，提交 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| 模型 | `SRV/models/Qwen3.8-Flash-Next-NVFP4-overlay`（只读） |
| 生产服务 | 481，监听 `172.16.108.9:8095`，供局域网用户使用。当前审批号 `RESTORE481-MORNING-20261011-09`，观察器运行到 2026-10-12 09:00 |
| 硬件 | 1 张 RTX 4090（24 GB）；双路 Xeon Silver 4310（48 线程，AVX-512 + VNNI，无 AMX）；内存 251 GB |

### 0.3 你的产出放在哪里

| 用途 | 服务器 | 本地镜像 |
|---|---|---|
| 代码、文档 | `SRV/development/gemini_oom_hybrid_20261011/`（下称 WORK） | `LOCAL/development/gemini_oom_hybrid_20261011/` |
| 运行输出 | `SRV/runs/dev_gemini_oom_hybrid_20261011/`（下称 RUNS） | 不必镜像 |

不要在别人的目录里写文件。本指令里的 `/tmp` 只用于桩服务的临时端口文件。

### 0.4 红线（任何情况下都不得违反）

1. 不推送代码，不启动 Ollama，不改论文（`paper/`）。
2. 不修改发布版代码树、模型目录、其他人的工装与证据目录。只允许 `import` 或调用它们。
3. 不手动删 `/data2/_shared/gpu.lock`，不用 kill 结束不属于你的进程。停止生产服务只能用 §5.3 的命令。
4. 任何一步失败都**不重试**，按本文的失败路由处理。
5. 不把用户的邮箱或任何个人信息发给任何服务。
6. 在 Windows 上写要拷到服务器的 `.py`、`.json` 文件时，必须用 LF 换行（Python 写文件用 `newline="\n"`）。restore 包的门链会比对 SHA，CRLF 会让它失败。

### 0.5 协调日志

每完成一步，在 `LOCAL/plan/COORDINATION_LOG.md` 末尾追加一行：

```
- <时间戳> Gemini：<步骤号> <结果>（附关键 SHA256 前 12 位）
```

时间戳一律用服务器的真实时间：`ssh 9 'date "+%Y-%m-%dT%H:%M:%S+08:00"'`。不要估计，也不要事后补写。

---

## 1. 背景

### 1.1 OOM 现象

2026-10-11 中午的 window02 里，测试服务用的是生产配置（offload，与生产只差 host/port）。先跑完 X 单路和两路之后，再发一条 87K 的真实会话（prompt 87,379 token），两个服务（O1、O2）都发生了 CUDA OOM。

关键日志（`SRV/runs/dev_hybrid_verify_20261011/window02/service_O1/serve.log`）：

| 时刻 | 记录 |
|---|---|
| 加载模型前 | `Free memory before loading model: 23.11 GiB` |
| 初始化后 | `Free memory after initialization: 2.55 GiB` |
| 捕获 CUDA Graph 后 | `Free GPU memory after capturing CUDA graphs: 2.50 GiB` |
| OOM 时（第 137 行） | 申请 48 MiB，空闲 21.69 MiB；进程在用 23.27 GiB，PyTorch 已分配 22.49 GiB，**281 MiB 已保留但未使用** |

OOM 发生在 `models/qwen4_exp/model.py:176`，即 `forward_layer_major` 的层循环 → GDN 线性注意力 → `kernel/fla/chunk_o.py:146` 的 `torch.zeros_like(v)`。

两个对照情形都没有 OOM：

- 10-10 晚的窗口 A/B（W98K）：在新起的服务上，同一会话的冷 87K 请求（round-00，87,100 token）作为第一条请求发送；
- window02：同一条 LC1 请求发到 hybrid 服务。

注意：window02 的 LC1 是 round-01 经 AIPerf 发送的渲染文本，与 round-00 不是同一条请求，但规模相同。

### 1.2 主会话的第一轮推断（未实测）

- **为什么要这么多显存**：层优先预填（`forward_layer_major`，`model.py:148-185`）会把所有分块的隐藏状态同时留在显存里。模型 `hc_count=4`、`hidden_size=2560`，每 token 约 2560 × 4 × 2 B ≈ 20 KB，87K 约 1.7 GiB。再加上各层内核的临时缓冲，预填期间要多用约 2.3 GiB。
- **为什么不够**：启动时按 `memory_ratio=0.88` 留下的余量只有约 2.5 GiB，没有按窗口允许的最长输入（98,304）计算。之前请求留下的 281 MiB 碎片吃掉了这点余量。
- **推论**：冷启动的 95K 请求即使在新服务上也可能 OOM。

### 1.3 hybrid 的问题

hybrid 在同窗口里单路快 21%、两路每路快 55%，但它**不是无损的**，原因有三：

1. CPU 路径走 W4A8，激活被量化为每 16 元一组的 int8；
2. 输出取决于缓存状态；
3. 同一服务内重复同一请求，输出也会不同。

本次要验证一种"可复现 hybrid"配置能不能保住收益：

- `--moe-hybrid-max-fetch 0`：永不经 PCIe 取数，GPU 上的专家集合不再变化（发布版 `server/args.py:758-768` 的帮助文字："0 = never fetch (all misses on CPU)"）；
- 环境变量 `FREETOKEN_CPU_MOE_NO_VNNI=1`：关闭整个 W4A8 系列，回到"faithful fp32"计算（`kernel/csrc/cpu_moe/cpu_moe_ext.cpp:724-750`）。

---

## 2. 总览与时间

| 阶段 | 内容 | 是否占 GPU / 停 481 | 时间 |
|---|---|---|---|
| P1-G1 | OOM 显存模型与阈值预测（预登记） | 否 | 现在开始 |
| P1-G2 | 输入冻结（真实内容的长度阶梯与 X） | 否 | 同上 |
| P1-G3 | 窗口工装 `oh_window.py` | 否 | 同上 |
| P1-G4 | 恢复包 restore10 | 否 | 同上 |
| P1-G5 | 真实入口演练（桩服务，含正反对照） | 否 | 同上 |
| P1-G6 | 就绪记录 | 否 | P1 完成后 |
| P2 | GPU 窗口：6 个服务 | **是**，属于压力测试，用户已知情 | 开窗条件见 §5.1 |
| P3 | 结果报告 | 否 | 窗口结束后 |

---

## 3. P1：纯 CPU 准备（481 继续服务）

### P1-G1 OOM 显存模型（交付 `WORK/OOM_MEMORY_MODEL.md`）

只读代码，不运行模型。逐项写出**层优先预填**在 N 个未缓存 token 时的显存增量，并给出公式和 `文件:行号`：

1. **各分块隐藏状态**：`model.py:148-185`，包括 `hidden[k].repeat(1, self.hc_count)`。写出每 token 字节数。
2. **单层单分块的临时峰值**：`kernel/fla/chunk.py` 中 `chunk_gated_delta_rule_fwd` 产生的 g、o、A、w、h、v_new，结合 `chunk_o.py:146`，以及 QSA 注意力、MoE 预填。要分清：哪些随分块大小（4096）变化，哪些随 N 变化，哪些是常数。
3. **引擎侧分块方式**：`engine/engine.py:1090-1110`（`_build_layer_major_chunks`）、`1260-1280`（segment / subchunks），以及 `--max-prefill-length 4096` 的作用。写清楚是否存在一个能限制层优先分块数的现成开关（例如 `dev_layer_major_subchunks`），以及它是开发开关还是生产开关。
4. **余量的来源**：`engine/cache_budget.py`（全文）、`engine/engine.py:603-628`。写清楚 `(1 − memory_ratio)` 的余量是怎样算出来的，是否随 `max_seq_len_override` 变化。
5. **用实测校准**：用 §1.1 的数字反推"N = 87,379 时的增量"，与你的公式对照。
6. **预登记预测**（窗口开始前写死，事后不改）：
   - 新起服务（无碎片）时，能完成的最长冷输入 N_fresh；
   - 有约 281 MiB 碎片时的 N_frag；
   - 对 §4 的 S1、S2 每个梯级，给出"成功"或"OOM"的预测。
7. **修复方案草案**（只写方案，不改代码），至少比较以下三种，各写清代价与对默认路径的影响：
   - (a) 按 `max_seq_len_override` 和层优先的每 token 字节预留余量；
   - (b) 长输入把层优先分成若干批；
   - (c) 中间态放主存。

### P1-G2 输入冻结（交付 `WORK/inputs/` 与 `WORK/INPUTS.json`）

**X 输入**（短提示）：复制 `SRV/development/d10_reanalysis_20261010/closed_loop_20261010/inputs_X.jsonl`，SHA256 必须为 `f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162`。

- 单路用第 0 行；两路用第 0、1 两行；
- 这是 AIPerf 的 `single_turn` 格式；
- 注意：X 是模板生成的英文长提示，只用来测速度和复现性。

**长度阶梯**，全部取自真实 agent 会话 `/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/`：

| 名称 | 来源 | 目标 prompt token |
|---|---|---|
| L64 | round-00.payload.json 的唯一一条 user 消息，**按字符截取前缀** | 64,000 ± 300 |
| L80 | 同上，截取 | 80,000 ± 300 |
| L87 | round-00.payload.json 原样 | 87,100（录制值） |
| L95 | round-07.payload.json 原样（多轮真实会话） | 95,352（录制值） |

**截取方法**：

- 用 `SRV/venv` 里的 `transformers.AutoTokenizer.from_pretrained(<模型目录>)`，对 `messages` 加 `tools` 做 `apply_chat_template(..., add_generation_prompt=True)` 计数；
- 用二分法确定截取的字符数；
- 截掉的是消息尾部（问题文字丢失也没关系，本测试只看预填显存）。
- 服务器 venv 中的 transformers 版本为 5.15.1。如果 `apply_chat_template` 不接受 tools 参数，改用发布版自己的计数路径（`server/generation.py` 中的 `count_prompt_tokens` 所用的 `TokenizeManager`），并在 INPUTS.json 中注明实际用的是哪种方法。
- 对 L87、L95 也用同一方法计数，与录制值的差应 < 300；否则停下回报。

**冷请求标记**：

- 每次发送前，在 `messages[0].content` 最前面加一行 `[gemini-oom run=<run_id> step=<名称> n=<序号>]\n`，保证整条都是冷的、不命中缓存；
- 标记在发送时生成，不写进冻结文件。

**INPUTS.json** 记录：每个文件的源路径、SHA256、字符数、计数得到的 token 数（不含标记）、截取字符数。并在其中断言：

- round-00 只有 1 条 user 消息，内容 345,089 字符；
- round-07 共 15 条消息。

**KV 断言**：每个请求的 token 数加 `max_tokens`（32）不得超过 98,304。

### P1-G3 窗口工装（交付 `WORK/oh_window.py`、`WORK/PLAN.json`、`WORK/test_oh_window.py`）

#### 复用已有代码（只 import，不复制、不修改）

把 `SRV/development/kimi_phase2_20261011/hybrid_verify` 加入 `sys.path`，从 `hybrid_service` 导入：

- `load_d07`：载入 `SRV/development/d07_g3g4_prepare.py`，提供 `take_d07_gpu_lock`、`release_d07_gpu_lock`、`process_identity`、`require_gpu_idle`；
- `capture_birth`、`cleanup`、`idle`、`alive_members`。

这些函数在 window02 中实际运行过。`cleanup(proc, birth, d07, output, checks)` 会在 `output` 下用 `x` 模式写 `cleanup.json`，所以每个服务的输出目录必须是新的。

#### 每个服务的生命周期（顺序固定）

1. **前置检查**：`idle(d07, [("127.0.0.1", 8123)])`，同时确认没有 `ft serve` 进程，且 `/data2/_shared/gpu.lock` 不存在。
2. **取锁**：`owner = d07.take_d07_gpu_lock("GEMINI-OOM-HYBRID-20261011-<服务名>", 0)`。
3. **启动服务**：`subprocess.Popen(argv, cwd=<服务输出目录>, env=env, stdout=serve.log, stderr=STDOUT, start_new_session=True)`，然后 `birth = capture_birth(proc, d07)`。
   - env 以 `os.environ` 为底，**删除所有 `FT_DEV_` 开头的键**；
   - 再设置 `PYTHONPATH=/data2/FreeToken/wt/release-e2/python`、`MASTER_PORT=8096`、`CUDA_VISIBLE_DEVICES=0`、`PYTHONDONTWRITEBYTECODE=1`；
   - 最后加上该服务在 PLAN.json 中声明的额外环境变量。
4. **等待就绪**：每秒轮询 `http://127.0.0.1:8123/health`，直到 `status=="ok"` 且 `maintenance=="serving"`，上限 600 秒。serve.log 中必须出现 `moe_cache_size=` 行，记录其数值。
5. **执行阶段**：按 PLAN.json 依次执行该服务的各阶段（§4）。
6. **清理**：调用 `cleanup(proc, birth, d07, <输出目录>, [("127.0.0.1", 8123)])`。
   - 返回 True 才能 `d07.release_d07_gpu_lock(owner)`；
   - 返回 False 则保留锁、写 `CLEANUP_BLOCKED.md`、整个窗口中止，进入恢复（见 §5.6）。
7. **写终态**：写 `<输出目录>/terminal.json`，包含：服务名、各阶段状态、错误、清理结果、是否保留锁。

#### 启动参数（argv）

不要手写参数，以 window02 实际使用的参数为准，再加上本文规定的差异：

- **offload 基线**：`SRV/runs/dev_hybrid_verify_20261011/window02/service_O1/argv_diff.json` 中的 `actual`；
- **hybrid 基线**：`.../service_H1/argv_diff.json` 中的 `actual`。

工装启动每个服务前，把最终 argv 与生产参数逐项比较，写出 `argv_diff.json`。允许的差异只有：

1. `--host`/`--port` 改为 `127.0.0.1`/`8123`；
2. hybrid 的两处：绑核前缀 `numactl --interleave=all taskset -c 1,3-23,25,27-47`，以及 `--moe-strategy hybrid`；
3. HR 服务在末尾追加 `--moe-hybrid-max-fetch 0`。

生产参数取自 `SRV/development/kimi_phase2_20261011/hybrid_verify/BASELINE_OWNER_FREEZE.json` 的 `argv`。出现其他任何差异，工装拒绝启动。

#### 阶段类型

**`x_aiperf`**：X 的速度测量。

- 命令以 window02 的 `service_H1/x_single_1/command.json` 为模板，只改 `--input-file`、`--output-artifact-dir`、`--request-count` 与 `--concurrency`（单路 1/1，两路 2/2）；
- 单路的输入文件是只含第 0 行的新文件，按字节复制；两路用原文件；
- 超时 180 秒。

结果从 `profile_export.jsonl` 读取：

- 每个请求的速度 = 1000 ÷ `inter_token_latency` 的值（ms）；
- 完成 token 数必须是 256，结束原因必须是 `length`，否则记该阶段为 invalid；
- 任一路速度 < 7.8 tok/s 记为 abnormal，并停止该服务后续的速度阶段。

同时从 `raw_records/*.jsonl` 提取每个请求的**输出文本**：

- 按包的顺序，把 `choices[0].delta` 中的 `reasoning_content` 与 `content` 依次拼接（`tool_calls` 写成 JSON 后一并拼接）；
- 存为 `outputs.json`，记录每个请求的文本、字符数和 SHA256；
- 请求按 `x_request_id` 与输入行对应：单路就是第 0 行；两路请按 AIPerf 记录里的输入索引对应，对应不上就停下回报。

**`ladder`**：冷长度阶梯，用 venv-eval 中的 OpenAI SDK，流式发送。

- 依次发送 PLAN 中的梯级，参数为 `max_tokens=32`、`temperature=0`、`stream=True`、`stream_options={"include_usage": True}`，超时 600 秒。
- 每一级写一行 `ladder.jsonl`，包含：名称、标记、本地 token 数、`usage.prompt_tokens`、首包时间、结束原因，以及是否出现错误包。
- **OOM 判定**：流中任何一个数据包含 `"error"`，且错误信息包含 `out of memory` 或 `worker_restarting_after_oom`。
- 判定为 OOM 后，从 serve.log 截取该时刻前后约 40 行的 OOM 记录，存入 `oom_<名称>.log`；然后每 5 秒轮询 `/health`，记录恢复为 serving 所用的时间（上限 300 秒）。
- **出现第一次 OOM 后，本服务的阶梯立即停止。**它属于测量结果，不算失败，服务照常进入清理。
- 每级发送前后，用 `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits` 各记录一次显存。

**`warmup`**：两次不计成绩的预热请求。

- 用 `x_aiperf` 的单路命令发送 2 次；
- 输出目录名为 `warmup_1`、`warmup_2`；
- 结果不计入任何判定。

**`compare`**：输出比对，纯计算、不发请求。

- 比较 PLAN 指定的两份 `outputs.json` 中对应请求的文本；
- 写出是否相同、首个不同字符的位置、双方长度。

**`d0_read`**：只用于 S6。

- 等待 5 秒后读取 `<输出目录>/d0_decode.json` 与 `<输出目录>/d0_decode_steps.jsonl`（`FT_DEV_D0_PATH` 设为 `<输出目录>/d0`，文件名为该前缀加 `_decode.json`）；
- 计算每个请求排除前 16 步后的失误率：missing_total ÷ (步数 × 480)。如果这个字段名不存在，就写"字段不同"并附上原始键名；
- 同时计算 `fetched_per_layer`、`cpu_per_layer`。

#### 窗口总控

`oh_window.py --execute --plan PLAN.json --out <RUNS>/window01`，按 PLAN 中的服务顺序执行：

- 硬时限 6,600 秒，从总控启动时算起；剩余时间少于 900 秒时，不再启动新服务。
- 服务内某阶段失败：记录下来，跳过该服务剩下的阶段，进入清理，然后继续下一个服务。
- 清理失败：整个窗口中止。
- 全部结束后写 `<out>/summary.json` 与 `<out>/terminal.json`。

总控**不负责停止或恢复 481**，那是 §5 的独立步骤。

总控启动时检查以下前置条件，任一不满足就拒绝启动：

- 生产 -09 的 supervisor/service/monitor 进程都已不在；
- `172.16.108.9:8095` 可以绑定；
- 没有 `ft serve` 进程；
- -09 观察器已结束；
- `gpu.lock` 不存在。

#### 单元测试 `test_oh_window.py`

至少覆盖：

- argv 差异门：只放行允许的三类差异，其余一律拒绝；
- OOM 判定：错误包识别；
- 输出文本提取：同时含 reasoning、content、tool_calls 的情形；
- compare 的首个不同字符位置；
- KV 断言；
- 时限逻辑；
- D0 失误率计算。

### P1-G4 恢复包 restore10（交付 `WORK/restore10/` 与 `WORK/diff_restore10.txt`）

**模板**：`SRV/development/kimi_phase2_20261011/restore09/`（只读复制）。做法参照同目录的 `CPU_READINESS.md`，只做身份替换：

1. `cp -a restore09 WORK/restore10`，删除复制过来的 `EXECUTION_TIME_PREFLIGHT.json`（如果有）、`__pycache__`、`.pytest_cache`。
2. 在所有文本文件中，**只替换两个精确字符串**：`RESTORE481-MORNING-20261011-09` 改为 `RESTORE481-MORNING-20261011-10`，`ROLLBACK184-MORNING-20261011-09` 改为 `ROLLBACK184-MORNING-20261011-10`。不要做任何更宽泛的模式替换，例如只替换"-09"，否则可能误改日期或其他字段。
   - `run_dir` 改为 `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-10`，该目录事先必须不存在；
   - `observation_until` 保持 `2026-10-12T09:00:00+08:00`。
3. 按顺序重算，不能颠倒：
   1. 重写 `SOURCE_MANIFEST.json`，包括各源文件的 SHA256 和 `package` 字段；
   2. 写入 `DEPLOYMENT_APPROVAL.json`，其中的 `package_source_manifest_sha256` 等于新 `SOURCE_MANIFEST.json` 的 SHA256；
   3. 计算 `DEPLOYMENT_APPROVAL.json` 的 SHA256；
   4. 写 `ROOT_FINAL_REVIEW.json`：`approval_id`、`approval_sha256`、`package_source_manifest_sha256` 用上面的新值；`verdict` 为 `PASS`；`reviewer_role` 为 `root_independent_final_reviewer`；`pending_independent_review` 为 `false`；`independent_review_sha256` 等于**本指令文件**的 SHA256。本指令要先 scp 到服务器 `SRV/plan/`，确认与本地 SHA 相同后再填。
4. **验证**（CUDA 关闭）：
   - `cd WORK/restore10 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B -m pytest test_cpu_orchestration.py -q`，必须 7 passed；
   - 门链：`CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B -c "import approved_attempt as a; d=a.load(); print('GATE_CHAIN_PASS', d['approval_id'], d['observation_until'])"`，必须打印 `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-10 2026-10-12T09:00:00+08:00`。如果 `approved_attempt.load()` 的返回值不是这个结构，以它能完整走完 ROOT_FINAL_REVIEW 与 SOURCE_MANIFEST 的 SHA 链为准，并在 CPU_READINESS 中写明实际使用的命令。
5. `diff -ru restore09 restore10 > WORK/diff_restore10.txt`。**允许出现的差异**只有：
   - 09→10 的身份字符串；
   - `run_dir`；
   - `SOURCE_MANIFEST.json` 中的 SHA；
   - `DEPLOYMENT_APPROVAL.json` 的 `package_source_manifest_sha256`；
   - `ROOT_FINAL_REVIEW.json` 的四个哈希与身份字段；
   - `README.md` 的身份说明。

   出现其他任何差异，就判 G4 失败，**今晚整个窗口取消**（没有恢复包就不能停服）。
6. 全部文件 `chmod 0444`，目录保持可写。

### P1-G5 真实入口演练（交付 `WORK/REHEARSAL.json`，0444）

先写桩服务 `WORK/stub_server.py`，只用 Python 标准库（`http.server.ThreadingHTTPServer`）：

- `/health`：返回 `{"status":"ok","maintenance":"serving"}`，处于"重启中"时返回 `maintenance:"restarting"`；
- `/v1/models`：返回包含 `Qwen3.8-Flash-Next-NVFP4` 的列表，因为 AIPerf 可能会查询；
- `/v1/chat/completions`：SSE 流式输出，每 20 ms 一个 `reasoning_content` 片段，**恰好输出 `max_tokens` 个片段**，最后一个片段的 `finish_reason` 为 `"length"`；随后的包带 `usage`，其中 `completion_tokens` 等于 `max_tokens`，`prompt_tokens` 按"消息字符数 ÷ 3.6"估算。这样 X 阶段"256 token、以 length 结束"的检查在演练中也能通过。
- 可配置项：
  1. 输出文本是否确定（同一请求是否每次都相同）；
  2. 当 prompt 字符数大于阈值 T 时，先发 1 个空内容包，再发 `{"error":{"message":"worker_restarting_after_oom: OutOfMemoryError: CUDA out of memory ..."}}` 和 `[DONE]`，随后 8 秒内 `/health` 返回 restarting；
  3. 启动后在 serve.log 里打印一行 `moe_cache_size=2700`。

**演练模式**：`oh_window.py --rehearse --stub-threshold <T> ...`。只允许替换下面四项，其余全部走真实代码，包括 PLAN 解析、argv 差异门（对"本应启动的真实 argv"照样检查，再换成桩）、阶段执行、AIPerf 调用、SDK 阶梯、输出提取与比对、清理和报告：

1. 生产已停的前置检查 → 跳过；
2. GPU 锁的取与放 → 改为空操作，并记录调用；
3. `idle()` 中的 GPU 检查 → 只检查端口；
4. 服务的 argv → 改为启动桩服务。

实现时注意以下三点：

- **第 3 项必须改模块里的函数。**`hybrid_service.cleanup` 内部会调用同一模块的 `idle`，所以要替换 `hybrid_service.idle` 这个模块属性。只替换你自己代码里的局部引用不够，否则演练时 `cleanup` 仍会去查 GPU。由于 481 在服务，那次检查必然失败。
- **d07 对象只替换三个方法**：`take_d07_gpu_lock`、`release_d07_gpu_lock`、`require_gpu_idle`。`process_identity` 必须保留真实实现，`capture_birth` 和 `cleanup` 要靠它核对进程身份。
- **演练模式不得写真实锁文件**，也不得停止或启动任何生产相关进程。

| 演练 | 桩配置 | 必须得到的结果 |
|---|---|---|
| R1 正向 | 确定输出；T 设为超过 L95 | 6 个服务全部走完；所有 compare 为"相同"；阶梯全部成功；summary 正确 |
| R2 反向一 | 输出不确定（重复请求的第 100 个字符起不同） | HR 服务的 compare 判"不同"，首个不同字符为 100 |
| R3 反向二 | T 设在 L80 与 L87 之间 | S1 阶梯在 L87 判 OOM 并停止；恢复耗时约 8 秒；S2 第一级 L95 判 OOM |
| R4 清理 | 正常 | 每个服务清理后，桩进程组全部消失，8123 端口可绑定 |

R1–R4 的命令、结果，以及全部源文件的 SHA256，都写进 `REHEARSAL.json`。任何一项不符就修改工装，直到通过；修改之后四项都要重跑。

### P1-G6 就绪记录

写 `WORK/CPU_READINESS.md`，包括：

- G1 至 G5 的交付清单与 SHA256；
- pytest 输出；
- 预登记预测，引用 OOM_MEMORY_MODEL.md 的 SHA；
- PLAN.json 全文。

然后在协调日志写一行"Gemini：P1 就绪"。

---

## 4. 窗口计划（PLAN.json 必须与本表一致）

| 顺序 | 服务 | 类型与 argv 差异 | 额外环境变量 | 阶段 |
|---|---|---|---|---|
| S1 | O-warm | offload 基线 | — | warmup → x_aiperf 单路 ×2 → 两路 ×2 → ladder [L64, L80, L87, L95] |
| S2 | O-fresh | offload 基线 | — | ladder [L95, L87]（不预热；先测最长的一级） |
| S3 | HR-a | hybrid 基线 + `--moe-hybrid-max-fetch 0` | — | warmup → 单路 ×3 → 两路 ×2 → compare：单路 1 对 2、1 对 3，两路 1 对 2 |
| S4 | HR-b | hybrid 基线 + `--moe-hybrid-max-fetch 0` | `FREETOKEN_CPU_MOE_NO_VNNI=1` | 同 S3 |
| S5 | HR-b-fresh | 同 S4 | 同 S4 | 单路 ×1（不预热）→ compare：本服务单路 1 对 S4 单路 1 |
| S6 | H-stats | hybrid 基线（与 window02 H1 相同） | `FT_DEV_D0=1`、`FT_DEV_D0_PATH=<输出目录>/d0` | 两路 ×1（不预热）→ d0_read |

**说明：**

- **S1 的速度阶段**是同窗口的 offload 参照，所有速度比值都以它为分母。
- **S6 带埋点**，速度不计入，只用来测 hybrid 两路的失误率。
- **阶梯要在服务内按顺序发**，因为前面的请求会改变显存碎片状态，这正是要测的。

**预计耗时：**

| 项 | 时间 |
|---|---|
| offload 加载，每次 | 约 4 分钟 |
| hybrid 加载，每次 | 约 5 分钟 |
| X 阶段，每次 | 15–30 秒 |
| 冷长请求，每次 | 15–25 秒 |
| 合计 | 约 55–70 分钟（上限 6,600 秒） |

---

## 5. P2：GPU 窗口

### 5.1 开窗条件（18:30 起开始逐项检查，全部满足才开窗）

1. P1-G4 通过，P1-G5 的 R1–R4 全部通过，协调日志已有"P1 就绪"。
2. 本地 `LOCAL/plan/GEMINI_STOP.md` 与服务器 `SRV/plan/GEMINI_STOP.md` 都不存在。主会话复核 P1 时如发现问题，会写这个文件；没问题就不写，也不回复。
3. 当前时间不早于 19:30。
4. **不与 Codex 的停顿测量冲突**。Codex 要在生产 481 上做一次约 15 分钟的测量（指令 `plan/CODEX_D11_P0_STALL_BASELINE_20261011.md`），满足以下任一条件即可：
   - (a) 协调日志里已有 Codex 写的"D11-P0 测量完成""D11-P0 今日不测"或"production_busy"；
   - (b) 当前不早于 21:00，并且服务器上没有 `stall_probe.py` 进程（`pgrep -f stall_probe.py` 为空），`SRV/runs/dev_d11_p0_20261011/` 下最近 10 分钟也没有文件更新。

   **如果到 22:00 仍不满足**：今晚不开窗，写"Gemini：P2 今晚取消（与 D11-P0 冲突未解除）"，等主会话改期。
5. `env | grep -E "^(FREETOKEN_|FT_)" | wc -l` 的结果为 0。

### 5.2 提前结束 -09 观察器

1. 读取 `SRV/runs/production/RESTORE481-MORNING-20261011-09/overnight_observation/start.json` 中的 `observer_pid`（当前为 1865057）。
2. 用 `ps -o pid,ppid,pgid,args -p <pid>` 找到它的父进程 `post_night_observer.py` 和进程组。
3. 核对：两个进程在同一个进程组，命令行分别包含 `post_night_observer.py` 和 `restore09/observe_overnight.py`。
4. 统计 `samples.jsonl` 的行数，并按 `restore09/observe_overnight.py` 中 `eligible()` 的同一组判据，逐行检查是否全部健康。
5. 执行 `kill -TERM -<进程组号>`，等待 3 秒，确认两个进程都已退出。
6. 写 `WORK/evening/OBSERVER_EARLY_STOP.json`，包括：时刻、采样数、是否全部健康、`samples.jsonl` 的 SHA、原因（"用户批准的 Gemini 窗口"）、`terminal_json: "absent_by_design"`。

**失败处理：** 身份核对不符就不杀进程，停下回报。TERM 之后 10 秒仍有进程存活，不要用 KILL，停下回报。

### 5.3 停 481

```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore09 && /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```

**成功判据：**

- 退出码 0；
- `SRV/runs/production/RESTORE481-MORNING-20261011-09/stopped.json` 存在；
- `SRV/run/production.active.json` 不存在（注意路径是 `run/`，不是 `runs/`）；
- `/data2/_shared/gpu.lock` 不存在；
- `nvidia-smi --query-compute-apps=pid --format=csv,noheader` 输出为空。

**失败处理：** 后续 GPU 步骤一律不做。按 §5.6 判断是否需要恢复：481 仍在服务就不用恢复；481 已停但状态异常，就走恢复流程。

### 5.4 执行窗口

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011 && CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python -B oh_window.py --execute --plan PLAN.json --out /data2/FreeToken/runs/dev_gemini_oom_hybrid_20261011/window01'
```

总控自身不使用 GPU，所以设 `CUDA_VISIBLE_DEVICES=`；各服务的环境里另行设为 0。

窗口运行期间，服务器上**不跑**任何其他 CPU 重任务。

### 5.5 恢复 481（用 restore10，三步，不要用 `deploy_conditional.py --execute`）

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10 && /data2/FreeToken/venv/bin/python start_approved_release.py'
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10 && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py'
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10 && setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-10/observer_outer.log 2>&1'
```

**成功判据：**

1. 第一步退出码 0；
2. 冒烟回执 `exit_code=0`、`classification=passed`，与 df77cb 基准逐字段一致；
3. `/health` 返回 serving，`backend_epoch=0`；
4. 观察器的 `start.json` 已写出。

**任一步失败**：走回滚。

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10 && /data2/FreeToken/venv/bin/python -c "import subprocess; from deploy_conditional import recover_after_restore_failure; raise SystemExit(recover_after_restore_failure(subprocess.run))"'
```

回滚也失败：写 `WORK/PRODUCTION_DOWN.md`，并在协调日志标"紧急"。

### 5.6 失败路由汇总（所有步骤都不重试）

| 情况 | 处理 |
|---|---|
| 5.1 条件不满足 | 不开窗（第 4 条的处理见 5.1） |
| 5.2 失败 | 不停 481，回报 |
| 5.3 失败，481 仍在服务 | 不恢复，回报 |
| 5.3 失败，481 状态不明 | 走 5.5 |
| 某服务启动失败或阶段失败 | 工装自动记录，继续下一个服务 |
| 清理失败、GPU 锁未释放 | 窗口中止。轮询 120 秒；仍未释放，写 `CLEANUP_BLOCKED.md`，**不能**走 5.5（GPU 被占着，恢复必然失败）。在协调日志标"紧急"，等主会话 |
| 窗口超过时限 | 工装自动停在当前服务之后，走 5.5 |
| OOM | 是测量结果，不是失败 |

---

## 6. 预登记的判读规则（窗口前写死，事后不改）

### 6.1 OOM

- 列出 S1、S2 每个梯级的实际结果，与 G1 的预测逐一对照。
- 预测与实测不一致的地方，写"模型待修正"，不能改预测。
- 合理性检查：S1 的 X 单路速度应在 29.62–30.19 的 ±5% 以内，两路每路应在 16.81–16.98 的 ±5% 以内（window02 的 offload）。超出范围就标"环境漂移"，所有速度结论降级为"仅供参考"。

### 6.2 可复现性

某个 HR 变体判为"可复现"，必须同时满足：

- 该服务的单路 1 = 2 = 3；
- 两路 1 = 2；
- 仅对 HR-b：S5 新起服务的单路与 S4 单路 1 也相同。

各项都逐字比较。只要有一项不同，就判"不可复现"，并写明首个不同字符的位置。

### 6.3 速度

以 S1 为分母，报告 HR-a、HR-b 的单路与两路每路比值。

| HR 两路每路比值 | 读法 |
|---|---|
| ≥ 1.10 | 可复现 hybrid 仍有收益 |
| 0.95–1.10 | 收益不明显 |
| < 0.95 | 比 offload 慢 |

单路比值只报告，不作判定。

### 6.4 hybrid 两路失误率

S6 排除每个请求前 16 步后的失误率，与算法研究的预测（29–31%）对照。

- 落在 27–33% 之间，记为"预测成立"；
- 否则记为"预测不成立"。

同时报告 PCIe 取数份额，与 D08 的 0.238 对照。

---

## 7. P3：结果报告

写 `WORK/RESULT.md`，包括：

- 每一步的终态和时刻；
- OOM 预测与实测对照表；
- 可复现性判定表；
- 速度表，含 window02 的 H1（35.55–36.59 / 25.96–26.27）作跨窗口参照；
- S6 失误率；
- 恢复冒烟结果；
- 全部证据的 SHA 索引；
- 与本指令不一致之处，**含任何 failed_harness 的根因**。必须打开原始记录查清，不能凭标志位推测。

然后在协调日志写一行"Gemini：窗口结束，等主会话复核"。

---

## 8. 主会话下发前自检（逐条）

| # | 检查项 | 结论与依据 |
|---|---|---|
| 1 | 开关名与语义是否在代码里核实 | `--moe-hybrid-max-fetch 0` = 永不取数（`server/args.py:758-768`）；`FREETOKEN_CPU_MOE_NO_VNNI=1` 关闭整个 W4A8、回到 fp32（`cpu_moe_ext.cpp:724-750`）；`FT_DEV_D0` 由 `moe/offload_cache.py:33-40` 定义，文件定期刷新（`:369`、`:376-401`）。`--moe-collect-stats` 不是命令行参数，所以改用 D0 |
| 2 | 负载内容是否核查 | 阶梯全部取自 seed_real 真实会话（round-00 共 345,089 字符，round-07 共 15 条消息）；X 是模板生成文本，只用于速度与复现性，已注明 |
| 3 | KV 容量 | 单请求最大 95,352 + 32 < 98,304；两路 X 各约 1.2K |
| 4 | 失败路由逐项写出 | 见 §5.6；OOM 明确不算失败；清理失败时不走恢复 |
| 5 | 停服窗口关键路径上没有人工环节 | 开窗条件全部机械可查；主会话的否决用 STOP 文件 |
| 6 | 与其他指令是否冲突 | Codex D11-P0 需要 481 在服务，以 §5.1 第 4 条避让；Codex 的放行条件写死审批号 -09，主会话已另发补充，允许 -10 |
| 7 | 真实入口演练与反向对照 | §P1-G5：R2 证明能看出不可复现，R3 证明能看出 OOM，R4 证明清理有效 |
| 8 | 时间安排 | 现在开始 CPU 准备；不早于 19:30 开窗；窗口 55–70 分钟，上限 110 分钟；22:00 仍无法开窗就取消；481 停服约 1.5 小时，属于压力测试，用户已知情 |
| 9 | 判据预先登记 | §6 全部写死；OOM 只作诊断，不设通过线 |
| 10 | 已知风险 | 6 个服务的总时长比 window02 长，所以设了时限与"剩余少于 15 分钟不再启动新服务"；S6 的 D0 文件字段名有不确定性，已要求按原始键名如实记录。HR-b 走 fp32 路径，可能明显变慢；若低于 7.8 tok/s，会被记为 abnormal 并停止该服务的速度阶段，可复现性比对也会缺数据，这种情况如实报告即可 |
| 11 | 自查中发现并已修正 | (a) §1.1 原写"同一条 87K 请求在新服务上没有 OOM"不准确：W98K 发的是 round-00，window02 发的是 round-01 的渲染文本，已改正。(b) 演练替换 `idle()` 时，必须替换 `hybrid_service` 模块里的函数，否则 `cleanup` 内部仍会查 GPU，演练必然失败，已补充。(c) 桩服务原来没写"恰好输出 max_tokens 个片段、以 length 结束"，X 阶段的 256 检查在演练中会失败，已补充；同时补了 `/v1/models`。(d) restore10 原写"09→10 替换"太宽泛，改为只替换两个精确字符串（已核对 rollback 编号为 `ROLLBACK184-MORNING-20261011-09`）。(e) 补了 tokenizer 的备用计数方法（已核对服务器 transformers 为 5.15.1）。门链命令 `approved_attempt.load()` 已核对：用 `python -c` 运行时 `sys.argv[1:]` 为空，不会触发"禁止重试"的检查 |
