# 待用户决策独立审计（2026-10-07 20:41）

## 结论

当前没有可立即提交用户批准的 GPU 启动包。仍保留两项**将来必须由用户决定**的测量后补跑；两项的 CPU/来源准备均未完成启动前的全部链路，不能把它们作为现在的审批结果提交。未发现第三项新的用户决策。

## 将来需用户裁定的两项

| 事项 | 首个失败项与为什么必须用户裁定 | 当前准备是否已构成可审批结果 | 建议与影响 |
|---|---|---|---|
| **E2-R046e：补跑 R046d 后未完成的 G3/G4+T06** | R046d/b89 已获用户批准并执行；G3-on 完成预填后第 8 个 decode 因 route-trace 队列满而 worker 退出，属于测量已开始后的工装失败。此前 R046d 的批准不覆盖新一次 GPU 重试。见 `development/PENDING_USER_DECISIONS_20261007.md:9,12,27-29`。 | **尚不可审批。** 背压 CPU 证据仍只是 Linux 17 PASS/1 GPU skip；新候选的 T16 默认路径、正式入口 CPU、同入口 FILEDRY、独立 R 启动签尚未齐全。`plan/COORDINATION_LOG.md:20:11` 也记录 R062 尚缺正式入口 CPU/R 签；之后的 r059 闭包依赖缺失是工装修复，非新测量失败。 | 完整启动包形成后，建议用户批准“仅补 G3/G4+T06，G3-off 保留；98,304/.88；G3 暂停关闭；双方同配置”。影响是获得合格 T06 画像并恢复 R049 前置；不得把既有 8 decode 步当作通过。 |
| **E2-R040b：仅补 R040a 未完成的 D16 项** | R040a/b88 的六锚点已完成保留；首个 native_slots_2 在观察器过早读取 `Batch.input_ids` 时失败，属于测量开始后失败。新轮只可补 D16 双批槽、停靠、缓存、交错，不能重跑六锚点。见 `development/PENDING_USER_DECISIONS_20261007.md:10,12,28`。 | **尚不可审批。** v9 已有 17-role source review `31f1fb77…` 和正式入口 Linux 5 PASS，但同入口 FILEDRY 与独立启动 R 签仍待；因此 CPU 修复不是可启动授权。 | 完整启动包形成后，建议用户批准“仅执行剩余 30 个 D16 startup，六锚点维持 R040a 封存结果”。影响是补足 T20/D16 交付，不重写旧封存，也不扩大测量范围。 |

## 已授权或仅为内部待办（不需用户再裁定）

- **R059 口径纠正**：仅判据口径错误可直接修正，保留原版，不重跑 GPU；已封存，不能重新列入待决。`plan/CODEX_HANDOFF_20261006.md:264-266`。
- **OOM 恢复（R060/R061）**：§14 已批准其默认门及故障注入；R060b/b92 已四臂完成，独立 terminal review 为 PASS/proposed kept，但尚待 D04，属于复核/封存，不是用户决策。其 round.json 尚未出现也不改变授权性质。`plan/CODEX_HANDOFF_20261006.md:268-272`；`development/PENDING_USER_DECISIONS_20261007.md:17,33`。
- **R062 当前 CPU 闭包缺少 `r059_d07_owned_launch` 源依赖**：这是未测量前的工装修复，未发生新 GPU 失败，不触发用户审批。
- 普通 CPU 修复、source review、FILEDRY、启动前 R 复核及 D04 封存均可由 root 完成；R049 缺 T06 画像是依赖，不是决策。`development/PENDING_USER_DECISIONS_20261007.md:18-19`。

## 尚未到审批阶段的事项

- `release/e2`、生产部署、远端推送：仅在全部任务完成并形成发布汇总后逐项询问；当前不得执行。`plan/CODEX_HANDOFF_20261006.md:274-281`。
- 未来才触发的升级：`not_met`/改判、发布配置改变、超出已授权的产品默认路径修改，以及新的测量后失败重试。`development/PENDING_USER_DECISIONS_20261007.md:21-23`。

## 审计边界与依据

- 权威优先级为交接书 §14；其规定全部任务完成后才汇总发布裁定，且 OOM 恢复不阻塞 R046c 和后续队列。`plan/CODEX_HANDOFF_20261006.md:260-281`。
- PLAN §8 将用户/审查方定位为裁定与轮次分配方，R 泳道负责启动前复核和轮后封存；协调日志须真实时间只追加。`plan/PLAN_20261005_重新规划.md:216-226`。
- 本审计只读当前文档及小型封存元数据；未连接监听端口、未使用 GPU、未取得锁、未读取原始大文件。

## 2026-10-08 CPU/FILEDRY 证据补充

- **E2-R049a 不新增用户决策。** v9 已完成受控 Linux CPU/FILEDRY：`/data2/FreeToken/runs/dev_T21/r049a_v9_cpu_20261008_020000/cpu_report.json`，SHA `5fd2e42e41237347199cd1dbf808af3653d3985aa3dc1b0a47ed10338e11355b`；CPU pytest 32 passed，日志 SHA `66d3c9a709527335423748f2d6bd3573e24149b0b789a02e9ec39ed4eaabcafc`。同入口 FILEDRY 回执为 `/data2/_shared/runs/ft_rounds/.filedry_E2-R049a_v9_sourceclosure_r2/dry_run_receipt.json`，SHA `6867980e3c0891c9e66714cbd86eb97f1081b731f80fc2b735c9ffdbb4d1355d`；未创建正式 RID、未启动服务、未发送请求、未取锁或分配 batch。该回执实际绑定 E2-R049 failed_harness D04 闭包的 independent review、0 accepted groups、4 partial unaccepted workloads 和 retry=false，仍不能替代 GPU 测量或解除 R046c/T06 前置。
- **E2-R040b 仍不进入用户审批。** collector 17-role source review 由实际 `verify_source_review` 通过：`/data2/FreeToken/runs/dev_D16/R040e_collector_source_review_v1/review.json`，SHA `64e76b5c1fe87fc1c5d6ca2c2109633f992cf45bf76b4143515b20012895a789`；绑定 CPU report SHA `b5a08d211d400205f78189e6ed89ffef8daf29ab821cdfcd9a5566bd361d45be` 与 source MANIFEST SHA `7bab7641cd399bddca8077879c155cb89300b7e9fb4faabd30d14061a7e4c6fd`。结论仅 `source_execution_ready=true`、`model_admitted=false`，不构成 GPU 启动许可。
