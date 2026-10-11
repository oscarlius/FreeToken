# 部署冒烟失败诊断与修复（Claude，2026-10-09 15:42 起，时限 1 小时）

只读诊断加 CPU 侧修复；未连接服务器（本机无 SSH 凭据），未启动服务，未改产品源码。

## 结论

**DEPLOY-E2-20261009-COND-01 的冒烟失败是判据错误，不是候选缺陷。** 481d3a7 在生产配置下的输出与发布门测试逐字节一致。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 长请求正文 SHA | `9845c3860e326f43…`，与 R040j interleave_3、R065 A1、R066a B 三次发布门冷跑相同 | `deploy_conditional_20261009/evidence_failed_release/smoke_first/long.json` |
| 失败后未执行的检查（离线补跑） | 短、长两条：finish=length、usage 512/128/640 与 8257/128/8385、正文非空、无 U+FFFD/代理/非法控制字符、API cached 缺失（null）——全部通过 | 同目录 `short.json`、`long.json` |
| 失败断言 | `validate_cold_rows` 要求行数 = ceil(8257/4096) = 3，实际 2 行 | `smoke_first.pytest.txt` |

## 为什么是 512 + 7,745

- 冒烟长提示（`r065_d16_discriminate_v1/inputs.json` 的 `long`）是带聊天模板的 Agent 提示：系统消息在第 2,051 字符以 `<|im_end|>` 结束，第 2,062 字符起 `<|im_start|>user`，约对应第 512–515 个 token。
- 发布 argv 含 `--enable-special-token-ckpt`；`scheduler/prefill.py` 的 D3 规则把块封顶在最后一个锚点的页对齐边界（page_size 64 → 512），剩余 7,745 由 D1 层优先整段准入（`prefill.py:170-178`）。
- 短提示无特殊 token，1 行 512；R066b 的中性提示无锚点，8,284 记 1 行。
- **回滚 184c965 的同一长请求同样是 512 + 7,745。** 回滚冒烟通过只是因为它按 8192 分块，ceil(8257/8192) 恰好也是 2。
- 结论：切分由提示内容决定，与请求时序、版本无关，可复现；固定行数从来不是有效不变量。
- 证据边界：本机没有目标 tokenizer，锚点 token 下标按字符比例估算（约 3.65 字符/token），D3 机制据 `prefill.py:65` 注释与 argv 推断。两个版本、两次独立启动得到相同的 512 切点，已足以支持"可复现"；如需精确到 token，Codex 可在服务器上用目标 tokenizer 定位 `<|im_start|>user` 的下标。

## 已做的修复（本地 `development/release_e2_ops_v2/`，需 Codex 重新冻结并同步服务器包）

1. `test_smoke_live.py::validate_cold_rows`：去掉固定行数。`new_sequences > 1` 或 token 合计超过 prompt → `SmokeInvalid`（外来 prefill，重测不回滚）；行非空、cached 全 0、合计 == prompt，否则 AssertionError（回滚）。恢复冒烟比较基准时，先比 `backend_cache_rows` 行结构，再比 SHA 与 usage。
2. `monitor_health.py`：首次 serving 之前不计失败（冷启动 loading 持续数分钟属正常，本次部署在专家库加载期间误报了 `three_consecutive_health_failures`）；超过 1800 秒仍未 serving 告警一次 `startup_not_serving`；`stopped.json` 已存在（审批停服）时不再重复告警 `supervisor_exit`。
3. `test_cpu.py`：新增锚点切分在两种分块下通过、缓存命中/短缺/空行失败、超额判外来 prefill、监控冷启动/超时/审批停服共 7 个用例（含参数化）。本地 `test_cpu.py test_worktree_checks.py`：**55 passed、0 skipped**。
4. 真实日志回放（`scratchpad/replay_rows.py`）：481 短 [512]、481 长 [512, 7745]、184c965 短 [512]、184c965 长 [512, 7745] 在新判据下全部 PASS。
5. `DEPLOY_ROLLBACK_E2_DRAFT_20261006.md` 第 44 行改写为新判据。
6. 独立审查（code-reviewer）结论"小改后通过"，无 HIGH；已按意见修改：
   - 监控改看 `stop_<审批号>.json`（`release_control.stop()` 在 SIGTERM 前写）判断审批停服；`stopped.json` 在崩溃时也会写，不能用。
   - `new_sequences != 1`（含 0）判外来 prefill。
   - 基线比较抽成纯函数 `compare_with_baseline`，旧基线缺行结构时报 AssertionError 而非 KeyError。
   - 手册写明外来 prefill 的判定条件，以及每个候选只允许一次 smoke_invalid 重测，第二次按失败回滚。
   - 补测试：退出时刻才写入停服文件、崩溃路径、零序列行、基线结构与 SHA 比较。
   最终本地 **58 passed、0 skipped**；真实日志回放 4/4 PASS。

## 交 Codex 的后续

- 重新冻结 ops 包（test_smoke_live.py、monitor_health.py、test_cpu.py 的 SHA 变了），Linux FT venv 复跑 CPU 全套，同步服务器包，独立审查。
- 首次部署成功后，`cold_baseline.json` 的 long 行结构应为 [512, 7745]，正文 SHA 预期为 `9845c386…`（本次实测值）；若不同，先报告再放量。
- `release_control.py:216` 在审批停服时也写一条 `supervisor_exit` 告警（带 approval_id）。是否改名为 `approved_stop` 由 Codex 决定。
- 发布说明已写 `_row_store` 仅 disk 后端需要；生产必须保持 `--ple-backend pinned`。
- 重新部署需用户批准（会停掉正在服务的 184c965）。
