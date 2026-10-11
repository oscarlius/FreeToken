# op-hak 任务 A：锚点切段开 / 关，真实轨迹逐轮首 token 对照预登记（2026-10-11，主会话 freetoken-06）

> 读者是执行者 op-hak。请**从头读到尾再动手**。遇到本文没写到的情况，就停下，在协调日志写明原因，等主会话处理。
>
> **本文件发出后冻结（0444），不再修改**；如需更正，主会话另发补充文件。
>
> **预登记**：`development/anchor_cut_accounting_20261011/PREREG_TASK_A.json`，SHA256 `0e1708bf033f26ec5f5cde94a1cd3ff86e786c854990033df8246a04006814b9`，下发前已封存。§6 的判读一律以它为准，事后不改。

---

## 0. 角色、环境与红线

### 0.1 角色

- **你（op-hak）**：执行者。写薄工装、在 CPU 上演练、执行 GPU 窗口、写报告。**只测量，不判定**；判定按 §6 机械套用。
- **主会话（freetoken-06）**：审核者。负责推演、预登记、复核。
- **用户**：拍板人。本指令已经用户确认后才推送给你。

### 0.2 环境

| 项 | 值 |
|---|---|
| 测试服务器 | `172.16.108.9`，从办公电脑用 `ssh 9 '<命令>'` 执行 |
| 本地仓库 LOCAL | `D:\00.开发\2026\03-模型实验\freetoken\freetoken\` |
| 服务器目录 SRV | `/data2/FreeToken/` |
| Python | `/data2/FreeToken/venv/bin/python` |
| 发布版代码 | `SRV/wt/release-e2`（481d3a70，只读） |
| 生产服务 | 481，`172.16.108.9:8095`，审批号 `RESTORE481-MORNING-20261011-10`，恢复包 `SRV/development/gemini_oom_hybrid_20261011/restore10/` |
| 用户规则 | 这台服务器**完全归测试使用**；有应用或业务争抢资源，可以停（见 W1） |

### 0.3 产出位置

| 用途 | 服务器 | 本地镜像 |
|---|---|---|
| 代码、文档（WORK） | `SRV/development/ophak_task_a_20261011/` | `LOCAL/development/ophak_task_a_20261011/` |
| 运行输出（RUNS） | `SRV/runs/dev_ophak_task_a_20261011/` | 不必镜像 |

### 0.4 红线

1. 不推送代码，不改论文，不启动 Ollama。
2. 只允许 `import` 或调用，不得修改：发布版工作树、模型目录、他人的工装与证据目录（含 `oh_window.py`、`restore10/`、`E2-R046g/`、`E1-R003-v2/`）、`plan/GEMINI_STOP.md`、`plan/GEMINI_D11_P0_STOP.md`。
3. 不手动删 `/data2/_shared/gpu.lock`；不用 kill 结束不属于你的进程（W1 清场按记录流程除外）。停生产只能用 W3 的命令。
4. 任何一步失败都**不重试**，按 §5 处理。
5. 不把用户的邮箱或任何个人信息发给任何服务。
6. 在 Windows 上写要拷到服务器的文件，一律 LF 换行；写中文文件后用 `open(f,'rb').read().decode('utf-8')` 自检编码。

### 0.5 协调日志

每完成一步，在 `LOCAL/plan/COORDINATION_LOG.md` 末尾追加一行，然后同步到 `SRV/plan/`：

```
- <时间戳> op-hak：<步骤号> <结果>（附关键 SHA256 前 12 位）
```

时间戳用服务器时间：`ssh 9 'date "+%Y-%m-%dT%H:%M:%S+08:00"'`。

---

## 1. 背景：为什么测

论文论点已冻结：**专家流遍数决定首 token**。本任务检验两件事：模型能否事先预测（支柱一），以及 M1"每轮只搬一遍"能否实测省时间（支柱三）。

1. **每个预填段都要把专家整池搬一遍**，短段也一样（`layers/moe.py:385-430` 无长度阈值）。生产单遍 2.7775 s（b167 `PARENT_b167/tax.json`，5 次中位数）。
2. **生产配置开着锚点切段**：`prefill_anchor_cut` 默认 True（`scheduler/prefill.py:179`），生产又开了 `--enable-special-token-ckpt`；锚点为 `<|im_end|>`、`</think>`、工具调用起始符（`scheduler/scheduler.py:186-210`）。
3. **生产实测**（`E2-D15-WINDOW-AB-20261010/W98K`）：seed_real 第 1–7 轮每轮切两段，第一段只有 64 或 128 个 token，预填 5.39–5.54 s；每轮复用的位置都是上一轮提示末尾，锚点那一段从没被用上。
4. **主会话的切段模拟器** `development/anchor_cut_accounting_20261011/segment_sim.py` 照搬上述代码规则：在 W98K 上 8/8 轮切段与复用位置完全一致；在 T2 的 C_edit 第 5–11 轮上，两段/一段的分档 7/7 一致。
5. **本次只改一个启动参数** `--no-prefill-anchor-cut`（`server/args.py:409`），零代码。预测：会变的轮次每轮省约一遍；不该变的轮次不变；复用位置两臂完全相同。

---

## 2. 测什么

### 2.1 服务（顺序固定，ABBA）

| 序 | 名称 | 锚点切段 | 启动参数相对生产的差异 |
|---|---|---|---|
| 1 | `A1_on` | 开（= 生产） | 只改 host / port |
| 2 | `B1_off` | 关 | 另加 `--no-prefill-anchor-cut` |
| 3 | `B2_off` | 关 | 同 B1 |
| 4 | `A2_on` | 开 | 同 A1 |

- 每个服务都是**新起的**，只服务本任务，结束即清理。
- 启动参数取 `SRV/run/production.active.json` 的 `argv` 原样，只允许三类差异：host 改为 `127.0.0.1`；port 改为空闲端口（例如 8123）；B 臂追加 `--no-prefill-anchor-cut`。写 `argv_diff.json`，出现其他差异就拒绝启动（可复用 `oh_window.compute_expected_argv` / `validate_argv_diff` 的做法）。
- 环境变量与 `oh_window` 起服务时相同，不得带任何 `FREETOKEN_*` / `FT_*` 开发开关。

### 2.2 每个服务内的请求（顺序固定，不得调换）

1. **warmup**：1 条短请求，不计成绩，只用来吸收服务的首请求初始化开销。payload 固定为 `{"model": "Qwen3.8-Flash-Next-NVFP4", "messages": [{"role": "user", "content": "warmup"}], "temperature": 0, "max_tokens": 8, "stream": true, "stream_options": {"include_usage": true}}`，**不带 tools**。不要改用带工具的输入（例如 `inputs_X.jsonl`）：带工具的请求与两条轨迹共享系统提示前缀，开锚点切段时会在共享前缀里留下快照，使 seed_real 第 0 轮命中缓存、两臂不对等。
2. **seed_real 第 0–7 轮**：payload 取 `/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/round-0k.payload.json` 原样，**只把 `max_tokens` 改为 32**。
3. **T2 第 0–11 轮**：trace 为 `/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json`（SHA256 `055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899`）。payload = `{"model": "Qwen3.8-Flash-Next-NVFP4", "messages": trace["rounds"][k]["messages"], "tools": trace["tools"], "temperature": 0, "max_tokens": 32, "stream": true, "stream_options": {"include_usage": true}}`。

**两条硬性要求：**

- **不得加冷标记**，也不得做任何改动 messages 的操作。轮次之间要靠原样前缀复用缓存；`oh_window.run_ladder_step` 会在第一条消息前加冷标记，本任务不能沿用。
- **并发 1**：前一条请求完全结束（收到 usage）后，间隔至少 1 秒再发下一条。

### 2.3 每条请求记录什么

- **首 token 时间**：从发出请求到收到第一个**非空**增量（`delta.content` 或 `delta.reasoning_content` 为非空字符串）的 monotonic 差，记为 `ttft_s`。第一个 SSE 分片通常是空的 role 包，不能拿它计时（`oh_window.run_ladder_step` 用的就是第一个分片，本任务不能沿用）。
- **用量**：`usage.prompt_tokens`、`usage.prompt_tokens_details.cached_tokens`、`usage.completion_tokens`。
- **切段**：本请求期间 serve.log 新增的所有 `Prefill batch` 行，解析出 `#new-token` 与 `#cached-token`，按顺序存列表。
- **输出**：全文与全文 SHA256。
- **OOM 迹象**：判定方法同 `oh_window.check_is_oom_chunk`。

**发送方式**：用 `httpx` 直接 POST JSON 到 `/v1/chat/completions` 并解析 SSE（`trust_env=False` 绕过 socks5 代理），不要用 OpenAI SDK 改写 payload；如果用 SDK，必须 `max_retries=0`。

---

## 3. P1：纯 CPU 准备（481 继续服务）

### H1 输入冻结（交付 `WORK/inputs/` 与 `WORK/INPUTS.json`）

把 20 个 payload（seed_real 8 个、T2 12 个）写到 `WORK/inputs/`，记录 SHA256。用 release-e2 的 `TokenizeManager` 与 `render_messages` 在本地计数（与 `segment_sim.py` 的 `render()` 相同），断言每轮 token 数与预登记的 `prompt_tokens` 逐轮相等：

- seed_real：87100、87328、87484、89295、90697、90940、93269、95352
- T2：12443、12737、13067、13272、13432、14103、19000、20143、21299、21338、21596、21976

任何一轮不等，就停下回报。

### H2 工装（交付 `WORK/task_a_runner.py`、`WORK/test_task_a_runner.py`、`WORK/stub_server.py`）

- 以 `import` 方式复用 `oh_window.py` 的启动参数门、OOM 判断、清理与 GPU 锁的做法，不复制、不修改。新写 §2.2、§2.3 的 replay 阶段。
- 单元测试至少 8 项，必须覆盖：非空首分片判定、`Prefill batch` 行解析、启动参数差异门（正反各一）、cached 提取、OOM 分支、超时、清理失败分支、ABBA 顺序固定。

### H3 恢复包 restore12（交付 `WORK/restore12/` 与 `WORK/diff_restore12.txt`）

按 `plan/GEMINI_OOM_HYBRID_20261011.md` §P1-G4 的同一流程，以 `SRV/development/gemini_oom_hybrid_20261011/restore10/` 为模板：

- 只替换两个精确字符串：`RESTORE481-MORNING-20261011-10` → `RESTORE481-MORNING-20261011-12`；`ROLLBACK184-MORNING-20261011-10` → `ROLLBACK184-MORNING-20261011-12`。
- `run_dir` 改为 `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-12`，该目录事先必须不存在。
- `independent_review_sha256` 填**本指令文件**的 SHA256（先 scp 到 `SRV/plan/`，确认两边一致后再填）。
- 验证：`pytest test_cpu_orchestration.py` 必须 7 passed；门链必须打印 `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-12 …`。
- **为什么用 -12 而不是 -11**：-11 已被暂停中的 D09 指令（Gemini）占用，避免两份恢复包同名。

### H4 真实入口演练（交付 `WORK/REHEARSAL.json`，0444）

桩服务按预登记返回 cached 和 serve.log 行，跑通全流程。另做三项反向对照，每项都必须被正确识别：

- (a) 首分片是空 role 包时，它不能被记为首 token；
- (b) 桩服务改为返回错误的 cached 时，报告能标出"复用不符"；
- (c) 桩服务注入 OOM 时，该服务中止且不重试，继续下一个服务。

### H5 就绪，停下等放行

写 `WORK/CPU_READINESS.md`，在协调日志写"op-hak：任务 A P1 就绪"。**然后停下**：开窗必须等主会话在协调日志写"任务 A 放行"。不得自行开窗。

---

## 4. P2：GPU 窗口（主会话放行后）

### W0 开窗条件（全部满足才开）

1. 协调日志已有主会话写的"任务 A 放行"。
2. Gemini 的 D11-P0 已有终态（协调日志里有完成、取消或否决），且 `pgrep -f stall_probe.py` 为空。
3. 本地与服务器的 `plan/OPHAK_TASK_A_STOP.md` 都不存在。
4. `env | grep -E "^(FREETOKEN_|FT_)" | wc -l` 为 0。
5. 生产 -10 在服务：`/health` 为 serving，`production.active.json` 的 `approval_id` 为 -10。

### W1 清场（用户规则：服务器完全归测试）

1. 记录 `nvidia-smi`、`docker ps`、`top -b -n1 | head -25` 到 `WORK/CLEARED.json`。
2. 除 481 和本任务外，凡持续占用 GPU、或 CPU 占用超过 50% 的进程或容器：先在 `CLEARED.json` 里记下 pid、完整命令行和恢复命令，再停止。
3. 系统进程不动；拿不准的不停，记下来回报。

### W2 结束 -10 观察器

同 `GEMINI_OOM_HYBRID_20261011.md` §5.2 的做法：先核对身份，再对进程组发 TERM；不用 KILL。

### W3 停 481

```bash
ssh 9 'cd /data2/FreeToken/development/gemini_oom_hybrid_20261011/restore10 && /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```

成功判据同 GEMINI_OOM §5.3：退出码 0；`stopped.json` 存在；`production.active.json` 不存在；GPU 锁已释放；GPU 计算进程为空。

### W4 执行窗口

按 §2 跑 4 个服务。总时限 60 分钟；窗口期间服务器上不跑其他 CPU 重任务。

### W5 恢复

1. 用 restore12 三步恢复 481：`start_approved_release.py` → `wait_release_and_smoke.py` → `post_night_observer.py`。判据同 GEMINI_OOM §5.5；任一步失败走同节的回滚。
2. 按 `CLEARED.json` 把 W1 停掉的东西恢复。

**预计耗时**：停服约 40 分钟（4 个服务 × 约 7 分钟，加恢复约 6 分钟）。并发 1，不属于压力测试。

---

## 5. 失败路由（所有步骤都不重试）

| 情况 | 处理 |
|---|---|
| H1–H4 任一失败 | 停下回报，不开窗 |
| W0 条件不满足 | 不开窗，写原因 |
| W2 / W3 失败，481 仍在服务 | 不恢复，回报 |
| W3 失败，481 状态不明 | 走 W5 |
| 某服务启动失败 | 记录，继续下一个服务 |
| 某服务 OOM | 该服务立即中止（481 每进程只自动恢复 1 次），**不重试**；继续下一个服务。OOM 是测量结果，不是失败 |
| 清理失败、GPU 锁未释放 | 窗口中止。轮询 120 秒；仍未释放，写 `CLEANUP_BLOCKED.md`，不得走 W5，在协调日志标"紧急" |
| 超过总时限 | 停在当前服务之后，走 W5 |
| W5 恢复失败且回滚也失败 | 写 `WORK/PRODUCTION_DOWN.md`，协调日志标"紧急" |

---

## 6. 判读（全部取自预登记，窗口前已封存，事后不改）

Δ 定义：同一轮，A 臂两个服务的首 token 均值减去 B 臂两个服务的均值。

| 项 | 判据 | 读法 |
|---|---|---|
| **S0 输入** | 每轮 `usage.prompt_tokens` 等于预登记 | 不等：该服务数据作废，记 failed_harness |
| **G1 结构** | 每轮 `Prefill batch` 行的 `#new-token` 序列，等于预登记的 `on_segments`（A 臂）或 `off_segments`（B 臂）；`cached_tokens` 等于预登记的 `cached`（两臂相同） | 任何一轮不符：写"模型在第 k 轮不成立"，照实报告。这是模型的失败，不是工装失败 |
| **G2 会变的热轮** | seed_real 第 1–7 轮、T2 第 1、4、5、6、7、8、10 轮，共 14 轮 | Δ 中位数在 [2.3, 3.0] s，且每轮 Δ ≥ 1.8 s：**成立**；中位数 < 1.0 s：**不成立**；其余：**部分成立** |
| **G2 阴性对照** | T2 第 2、3、9、11 轮 | Δ 中位数的绝对值 ≤ 0.3 s：**阴性对照成立**；否则写明 |
| **G2 漂移检查** | 同臂两个服务（A1 对 A2、B1 对 B2）同一轮的首 token 相差不超过 10% | 超过 10% 的轮次多于 3 个：标"环境漂移"，G2 降级为"仅供参考" |
| **G2 上下限** | 会变轮 Δ > 3.2 s 或 Δ < 0 | 标"异常、待诊断"，不登记为有效结果 |
| **冷轮** | 两条轨迹的第 0 轮 | 只报告 Δ，与预登记的预测区间对照（seed_real [-0.5, +1.5] s；T2 [2.0, 3.0] s） |
| **各轮绝对值** | 与预登记的 `on_ttft_band_s` / `off_ttft_band_s` 对照 | 只报告 |
| **G3 可复现** | A1 对 A2、B1 对 B2，同轮输出全文逐字相同（都是新起服务、同历史，属同类比较） | 不同：写首个不同字符的位置 |
| **G4 两臂之间** | ON 对 OFF 同轮输出是否相同 | 只报告。两臂切段结构不同，属论文 §10 的已知类别 |
| **G5 OOM** | B 臂 seed_real 第 0 轮（冷 87,100，单段）预测**不 OOM**，推算余量约 0.3 GiB | 若 OOM：按 §5 中止该服务；报告写"关闭锚点切段后冷 87K 单段 OOM"，这是生产相关发现；T2 部分仍按 G2 判读 |

---

## 7. P3：报告 `WORK/RESULT.md`（0444）

- 逐服务、逐轮一张表：`prompt_tokens`、`cached_tokens`、切段列表、`ttft_s`、输出 SHA 前 12 位。
- G1–G5 按 §6 机械给出结论。
- W1 清场与 W5 恢复记录；证据文件 SHA256 索引。
- 只写数据和按 §6 的读法，不加推测。完成后在协调日志写"op-hak：任务 A 窗口结束，等主会话复核"。

---

## 8. 主会话下发前的自检（逐条，附数字）

| # | 清单项 | 本指令的情况 |
|---|---|---|
| 1 | 代理指标到终点指标是否闭合 | 直接测每轮首 token，即用户感受到的指标，不经代理 |
| 2 | 样本是否独立 | 生产臂的切段规律已做过样本内校验（W98K 8/8、C_edit 7/7）。**关闭锚点切段**的结果和 4 个阴性对照轮从未测过，是真正的样本外预测 |
| 3 | 是否落在目标负载 | seed_real 是 87–95K 的真实会话，即目标负载；T2 是第二条独立的真实轨迹 |
| 4 | 判据是否预登记、有无停止条件 | 已封存 PREREG；有阴性对照，防止"所有轮都变快"这类混杂（如环境漂移）被误读成收益 |
| 5 | 理论上限 | 每个会变的轮次最多省一遍（约 2.78 s）；Δ > 3.2 s 判异常 |
| 6 | 合理性下限 | 会变轮 Δ < 0 判"异常、待诊断"，不登记为有效负结果 |
| 7 | 实现是否守住预测前提 | 只改 `--no-prefill-anchor-cut`；它只在 `prefill.py:179` 生效（读码，release-e2）；`special_token_ckpt` 照开，锚点集合仍在，只是不切；两臂复用位置相同由 G1 直接检验 |
| 8 | 今天的教训 | 等价判据用同类比较（G3：冷对冷、同历史）；ABBA；首分片可能是空 role 包；不加冷标记，以免破坏前缀；OOM 只自动恢复 1 次，首次 OOM 即中止；绕过 socks5 代理；SDK 不重试 |
| 9 | 与其他任务的冲突 | 等 Gemini 的 D11-P0 有终态再开窗（它在生产上测）；恢复包用 -12，避开暂停中的 D09（-11） |
| 10 | 风险 | B 臂冷 87K 单段 OOM 的余量只有约 0.3 GiB（推算）；处理办法已写进 G5 和 §5 |
| 11 | 停服影响 | 481 停服约 40 分钟；并发 1，不属于压力测试 |
| 12 | 自查中改正的两处 | (1) warmup 原定借用 `inputs_X.jsonl`，它带工具定义，与两条轨迹共享系统提示前缀；开锚点切段时会在前缀里留下快照，使 seed_real 第 0 轮命中缓存、两臂不对等。已改为不带工具的极短消息（与轨迹只共享 1 个 token）。(2) 漂移检查原定"A1 首 token ≤ 6.3 s"，但客户端首 token 含分词开销，没有实测依据；已改为 ABBA 同臂两服务互相对照（≤ 10%） |
