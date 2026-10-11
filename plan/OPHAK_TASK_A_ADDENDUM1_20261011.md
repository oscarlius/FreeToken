# op-hak 任务 A 补充 1：P1 复核结论、六点答复、W0 更正、恢复包改用 -11（2026-10-11 21:00，主会话 freetoken-06）

> 适用于 `plan/OPHAK_TASK_A_ANCHOR_CUT_20261011.md`（b8232e31efca…）。本补充优先于原指令中被它改动的条目；其余条目不变。发出后冻结（0444）。

## 1. P1 复核结论：通过

主会话独立核对了以下几项，没有只看执行者的自报：

| 项 | 核对内容 | 结论 |
|---|---|---|
| 工装 `task_a_runner.py`（f0210979…） | 首 token 只认非空的 `reasoning_content` 或 `content`（`absorb_chunk`）；payload 原样字节发送，并校验文件与 messages 哈希（`plan_item`）；`httpx` 设 `trust_env=False`、不重试；B 臂只多 `--no-prefill-anchor-cut`（`build_argv`，并与 `oh_window.compute_expected_argv` 交叉核对）；OOM 只中止该服务（`run_service` / `run_window`） | 符合 |
| warmup | `{"role":"user","content":"warmup"}`，不带 tools，`max_tokens` 8 | 符合 |
| 输入 | 20 个 payload 的 token 数与预登记逐轮相等；两条轨迹最长共享前缀 58 < 64，不会跨轨迹复用 | 符合 |
| restore12 | `diff_restore12.txt` 只含身份字符串、`run_dir`、重算的哈希、README 与 scope 说明 | 符合（但改用 -11，见第 4 节） |

## 2. 对 op-hak 六点的答复

1. **ROOT_FINAL_REVIEW 由执行者写入 PASS**：同意，与 restore10 的做法一致；差异由主会话独立核对。
2. **非 OOM 的请求错误**：同意"清场后停止窗口"。但**窗口不论以什么终态结束，都必须执行 W5 恢复 481**，并按 `CLEARED.json` 恢复 W1 停掉的东西。唯一例外是 `cleanup_blocked`（GPU 锁未释放），此时按原指令 §5 处理，不走 W5。
3. **漂移的相对差**：同意取 `|a − b| / max(a, b)`。
4. **W0 第 2 条（D11-P0 终态）**：更正，见第 3 节。
5. **启动参数门**：同意。改用 `compute_expected_argv` 加 `extra_argv`，再与 `build_argv` 交叉核对，等价且更严。
6. **B 臂冷 87K 单段 OOM**：同意，按原指令 G5 与 §5 处理。

另：本地 STOP 文件由操作者人工确认（CPU_READINESS §6 第 4 条），同意。

## 3. W0 第 2 条更正

原文"Gemini 的 D11-P0 已有终态"写得过严，是主会话的错误。D11-P0 至今没有开始（服务器上没有它的代码目录、输出目录和进程），硬等会让 GPU 空闲。真正要防的是两边同时占用 481，而不是先后顺序。

**改为**：

- **W0 第 2 条**：`pgrep -f stall_probe.py` 为空，且 `SRV/runs/` 下名称含 `d11_p0` 的目录在最近 10 分钟内没有文件更新（没有这类目录也算满足）。
- **新增 W3 前复查**：执行 W3 停 481 之前，再查一次 `pgrep -f stall_probe.py`。不为空就不停 481，写"任务 A 与 D11-P0 冲突"，等主会话。
- **工装同步修改**：`task_a_runner.py` 中 W0 第 2 条的自动检查（`TERMINAL_LINE_RE` 及 `w0_checks` 中对应项）按上面的新条件改写。只改这一处，改后重跑全部单测，并在协调日志记下新的 SHA。

## 4. 恢复包改用 -11（取代原指令 H3 的 -12）

**原因**：Gemini 的 D11-P0 预检脚本（`plan/GEMINI_D11_P0_PRECHECK_20261011.py` 第 11 行，SHA 已封进它的指令）只认 `-10` 和 `-11`。任务 A 若以 -12 恢复，D11-P0 之后就无法在生产上测。原指令避开 -11，是因为它留给了 D09 窗口；但 D09 已被 `plan/GEMINI_STOP.md` 拦住，并将按新设计重做，它的 -11 恢复包不会被使用。

**做法**：

1. 用你的 `build_restore12.py` 同一流程，以 restore10 为模板生成 `WORK/restore11/`：只替换两个精确字符串，`RESTORE481-MORNING-20261011-10` → `-11`，`ROLLBACK184-MORNING-20261011-10` → `-11`；`run_dir` 为 `/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11`。
2. `independent_review_sha256` 填**本补充文件**的 SHA256。
3. 验证：`pytest test_cpu_orchestration.py` 7 passed；门链打印 `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-11 2026-10-12T09:00:00+08:00`；`diff -ru restore10 restore11` 只含允许类别。
4. W5 执行前确认：`/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11` 不存在；如已存在，停下等主会话，不得改用 -12。
5. `restore12` 原样保留、不再使用，不要修改它。`CPU_READINESS.md` 已是 0444，不要改；另写 `WORK/CPU_READINESS_ADDENDUM1.md`，记下第 3、4 节的改动、restore11 的各项 SHA，并写明"restore12 已由 restore11 取代"。

## 5. 放行

本补充经用户确认后推送。主会话同时在协调日志写"任务 A 放行"。

你先完成第 3 节的工装修改和第 4 节的 restore11，在协调日志各记一行；然后按原指令 §4 从 W0 开始执行。W0 第 2 条按第 3 节判断，W5 用 restore11。
