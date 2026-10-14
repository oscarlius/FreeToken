# 发布 e3 结果报告（RESULT_E3，op-hak）

- 执行者：op-hak；服务器时间 2026-10-12。
- 依据：`plan/OPHAK_RELEASE_E3_20261012.md`（a52388caee321e59c26d24e0f71e584e9659bee97c560cb532699e76d0aeb137）；
  补充 1 `plan/OPHAK_RELEASE_E3_ADDENDUM1_20261012.md`（7fee5a520ad22a3651b72dec69697625064dc0a16625fe910ca4be226a51799c）；
  预登记 `PREREG_RELEASE_E3.json`（ee70f1ff45fd604890f85aa7e34491137d29d10268d345f2462d2065506db52c）；
  主会话放行（协调日志 2026-10-12T10:18:05+08:00）；P1 报告 `CPU_READINESS_E3.md`（e05e350371e7…）。

## 1. 结论

发布 e3 已上线：481 运行 release/e3（commit 9db0ee776c25…），参数 `--prefill-anchor-cut-min-tokens 32768`，审批 `RELEASE-E3-20261012-01`。
正式冒烟 passed（exit 0），W5 核对全部通过，观察器已启动，运行至 2026-10-13 09:00。未进入任何失败路由。

## 2. 时间线（服务器时间，2026-10-12）

| 时间 | 事件 |
|---|---|
| 10:21:03 | W1 开始：restore13 的 `stop_approved_restore.py` 停止 -13 |
| 10:21:24 | W1 返回 0；stopped.json 中 `resources_released: true`，`errors: []` |
| 10:22:57 | W2 开始：Q1 real 模式（全新 e3 服务，127.0.0.1:8123） |
| 10:28:26 | W2 结束：rc 0，classification passed；Q1 已关闭，gpu.lock 已释放 |
| 10:29:04 | W3 finalize：rc 0，`q1_check: passed` |
| 10:29:32 | W4 开始：`deploy_conditional.py --execute`（后台）；内部 W3.5 预检立即通过（`{"w35": "passed"}`）；10:29:33 start_approved_release 预检写出 execution_preflight.json |
| 10:33:39 | e3 在 172.16.108.9:8095 serving（serving_ready.json 写于 10:33:44） |
| 10:33:44 → 10:33:59 | 正式冒烟，exit 0 |
| 10:33:59 | 观察器启动，截止 2026-10-13 09:00 |

停服时长：从 W1 开始（10:21:03）到 e3 在局域网首次 serving（10:33:39），约 12 分 36 秒。
（协调日志第 2487 行记的冒烟完成时间 10:34:00 为估计值；以 smoke_execution_result.json 的 10:33:59 为准。）

## 3. Q1 逐项核对（W2）

| 项 | 结果 |
|---|---|
| 构建门 | 导入 `/data2/FreeToken/wt/release-e3/python/freetoken/scheduler/prefill.py`，通过 |
| 参数门 | serve.log 中 `prefill_anchor_cut_min_tokens=32768`，通过 |
| 短请求 SHA256 | `fd11a31559daaafb889b8a80f29a412470e0635caae631971a0a31e948a9dfdd`，**等于 e2 参考值 fd11a315…** |
| 短请求行结构 | [512]，cached 0；usage 512/128/640；finish_reason length |
| 长请求行结构 | [8257]，cached 0；usage 8257/128/8385；finish_reason length |
| 长请求 SHA256（只报告，不判定） | `8a44281763e9e8f65b1d18459f4699f901713596b8f60db39567e94bd6b7f3aa`；e2 为 9845c3860e…，不同（段数由 [512,7745] 变为 [8257]，预登记允许） |
| cold_smoke.json | SHA256 `021e2ab32f660e8bef7936f3fbc745a017d1f86521fcc84b16fcd457660e752f`，q1_mode `real`，0444 |
| 清场 | 服务已退出，gpu.lock 已释放，8095/8096/8123 无监听，显存 4 MiB |

## 4. finalize（W3）

- 输入：Q1 的 cold_smoke.json（上表哈希，已先记入协调日志）。
- 输出：`q1_check: passed`；manifest_sha256 9be618f419c8…；expected_reference.json 与 cold_baseline.json 已写入
  `release_e3_reference_20261012/`（0444）；cold_baseline SHA256 021e2ab3…。
- 审批：approval_sha256 6e6e6555…，review_sha256 03494cbb…；`require_root_final_review` 自检通过；`GATE_CHAIN_PASS`。

## 5. 正式冒烟（W4）

- `smoke_execution_result.json`：exit_code 0，classification passed；prompts [512, 8257]；开始 10:33:44，完成 10:33:59。
- 短请求 SHA 与 Q1 相同（fd11a315…）；长请求 SHA 与 Q1 相同（8a442817…）。
- smoke_gate.json 存在；正式冒烟内部按参考值逐项比较通过。

## 6. W5 核对

| 项 | 结果 |
|---|---|
| serve.log 中的参数 | `prefill_anchor_cut_min_tokens=32768`（出现 1 次） |
| production.active.json | approval `RELEASE-E3-20261012-01`，mode release，commit `9db0ee776c25afa8d2719ab700b2de7ccc606142` |
| argv | 与预登记 `argv.e3` 逐项相等（`True`） |
| 局域网健康检查 | HTTP 200，status ok，maintenance serving |

## 7. 上线前的分支与存档记录（§2.1、§2.2）

- 分支 `release/e3` = 9db0ee776c25…，`git status --porcelain --untracked-files=no` 为空；两个 `.so` 为普通文件（10a2bd8311b9…、07701be28030…）。
- 存档相对 v8 的差异（不含 evidence/）：`binary_manifest.json`（JSON 语义只改 release 的 path 与 commit）、`release_config.py`、
  `run_smoke.py` 与 `test_smoke_live.py`（各改参考值路径一行）、`test_redeploy_cpu.py`，以及新增的 `test_e3_release.py`。
- `d07_g3g4_prepare.py` 与 v8 逐字节相同（c4a28aaa…）。
- 审批的 `frozen_ops.source_manifest_sha256` = 9be618f4…（finalize 写入，与 evidence/source_manifest.json 一致）。

## 8. 失败路由记录

无。W3.5 通过；e3 启动、冒烟均成功；未调用 restore14，未调用 ROLLBACK184。

## 9. 已知限制与待记录事项

1. **restore14 自身在 owner 发布之前启动失败**：沿用 restore 包的冻结语义（先检查再回滚），不会自动恢复，需人工处理（补充 1 §4）。本次未发生。
2. **restore14 的 user_authority 仍为任务 B 的旧文字**（指令要求只做三类替换，按指令保持），原文如下（逐字）：
   > User-confirmed OPHAK_TASK_B_CUT_POLICY_20261011.md (sha256 64394da69f58c2b9f4f9aa169e3883f243991a3e12efab2411cfe3070cdb4186) GPU window: stop 481, run R0/C_A1/C_B1/C_B2/C_A2 (candidate m1/cut-min-tokens 9db0ee77, never deployed to production), restore 481 to release-e2 481d3a7; user instruction 2026-10-12 00:50 'task B continue'; main-session written release (COORDINATION_LOG '任务 B 放行') required before the window; no push; Ollama stays stopped.
3. **README "当前生产"段未更新**：§4 要求更新 `/data2/FreeToken/README.md` 的"当前生产"段，但 README 中不存在该标题（最接近的是"重新部署当前状态（2026-10-09）"）。未自行新建或改写，待主会话裁定位置与文字。
4. W5 人工停服路线：本次未使用。
5. 观察器：`observe_overnight` 本次正常运行（start.json 与 samples.jsonl 正常写入）。

## 10. 后续（§4）

- 观察器运行至 2026-10-13 09:00（pid 992641）。
- 12:00、18:00、次日 09:00 各查一次：OOM 与 worker 退出次数、请求数、热轮（cached > 0）的 Prefill 行数分布（只统计 `#new-seq: 1`）。
- 若某次检查发现 481 不在服务且原因为 OOM 或 worker 退出：先用发布包的 `stop_approved_restore.py` 清理，再用 restore14 恢复 e2（若已用过，按同样规则复制出 restore15），然后报告。

## 11. 文件位置

- 窗口记录：`runs/dev_release/release_e3_window_20261012/`（W1_*、W2_*、W3_finalize.*、W4_*、W4_watch.sh）。
- Q1：`runs/dev_release/release_e3_window_20261012/q1_real/`。
- 正式冒烟：`runs/production/RELEASE-E3-20261012-01/smoke_first/`；smoke_execution_result.json 位于同一 run 目录。
- 观察器：`runs/production/RELEASE-E3-20261012-01/overnight_observation/`。
