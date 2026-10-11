# T17 R033 独立复核与 D04 关闭设计

本文只描述 R033 的复核和归档门槛，不读取或裁定任何实测结论。结论来源应是该轮冻结的 `result.json`、逐 case 证据、`status_batchNN.json`、launch receipt 和独立复核 JSON；HTTP 成功、服务启动、CPU stage PASS 均不是测量通过。

## 可复用边界

- `t17_continuation_runner.verify_prerequisite()` 已验证 R032/b60 为 sealed `kept` 父门、候选提交、D04 history 和外层 closure binding。关闭器应重新调用等价检查，而不是相信 R033 启动时的旧结果。
- `equiv_suite.continuation.run_case()` 产出 warm、两次独立 fresh same-structure reference、冻结 schedule 及每 case 的 `gate.evaluate()` 输入；`gate.output_comparison()` 提供 token/text SHA 与首 token fork。
- `gate.handoff()` 给出四项 D2D restore role、首 layer-major child 的初始 state/坐标判定；`gate.evaluate()` 还要求两个 reference 的 PID/start-ticks/execution_id 不同、D0 structure 已验证、schedule SHA 和实际输入 SHA 与 warm 相同。
- `t16_r032_close.audit_first()/close()` 是优先模式：冻结独立 reviewer 后即时重算，比较保存 review JSON、保留 raw-file 哈希，再要求显式 immutable closure stage 和 audit receipt。
- `t17_r023_close.close()` 与 `t17_r027_d04_close.close()` 可复用 D04 顺序：拒绝已封闭目录和 symlink，复制 runtime/CPU/reviewer/closure sources 及 launch receipt，写 `review_batchNN.json`、`batch.sh`、`round.json`，调用 `round_close.sh`，再以 `round_json_append.py verdict` 和 `check` 固化 history/manifest，最后复核原始 raw 哈希和全树只读。

## R033 逐 case 判据

`failed_harness`：两次 reference 自身 token 或 text 不相同；reference 数量/独立进程身份/D0 structure/schedule SHA/输入 SHA 不完整；任何 required evidence reader、operator coverage 或结构校验抛错。R033 runner 还会把 `not_met` 但缺第一层 operator 诊断降级为 `failed_harness`。这类结论不得写成测量反例。

`not_met`：在 reference repeat 已通过的前提下，warm 与 reference token IDs 或完整 text 不同，或 `handoff()` 的四项 restore role / first-child 条件明确失败。应保存 warm/reference 比较、首 fork、精确输入 SHA、schedule/structure receipt、状态角色及已要求的 operator receipt；不得由仅 diagnostic 的后续实验覆盖。

`kept`：不是 runner 的直接输出。只有全部 28 个冻结 matrix cases 均为 `measurements_pass_pending_independent_review`，每 case 的 state handoff 和 same-structure reference 均 PASS，且独立复核重算相同证据并明确 PASS 后，D04 才可将 proposal 写为 `kept`。该 kept 仍只代表 R033/T17 定义的 continuation gate。

## 独立复核包

独立 reviewer 应在不复用 runner 内存对象的进程中：

1. 验证 launch receipt、PID/start-ticks 已终止、batch log、冻结 stage/report/source map、runner/template SHA、R032 closure binding，以及 R033 目录未预封闭。
2. 对每个 case 重读 endpoint、D0、schedule、state 和 operator 文件；验证文件非 symlink、SHA、所有 schedule/reference/input identity 绑定；重新调用 frozen `gate.handoff/evaluate` 或等价纯读取实现。
3. 检查 result/status 的 case 覆盖与重算结果逐项一致。对 `not_met`，独立复核须确认 reference repeat PASS 且差异确为 warm-v-reference；对 kept proposal，须确认完整 28 case 集合。
4. 输出只读 `review_batchNN.json`，至少绑定 RID、batch、candidate/parent、launch receipt SHA、CPU stage report SHA、runner/source/template SHA、每 case verdict、raw-file map、reviewer identity、`verdict: PASS`（表示复核通过，不替代 round verdict）。

## D04 关闭顺序

1. 在未写 `round.json`、`round_history`、`MANIFEST.sha256` 的 R033 目录执行 audit-first；拒绝活跃 batch/service、既存 close controls、外来 owner、可写或 symlink 证据。
2. 验证独立 review 的 SHA 与即时重算完全一致；验证专用 closure-stage 的 source/log/report 都是 readonly PASS。
3. 归档 launch receipt、原始 batch wrapper 到 `batch.sh`、CPU/runtime/reviewer/closure sources、冻结 inputs、schedules、case artifacts 和 D04 tools；以 `x` 模式写入，避免覆盖。
4. 写 pending-review `round.json`，执行 `round_close.sh` 生成 manifest/history 初始封存；再用 canonical `round_json_append.py verdict --new <kept|not_met>` 写最终 history，并运行 `check`。
5. 最后逐一比对 close 前 raw-file 哈希，检查 `MANIFEST.sha256`、history、review SHA 和整个目录无写位；输出 round/manifest/review SHA receipt。

## 风险与禁止推断

- `measurements_pass_pending_independent_review` 不是 kept；`diagnostic_missing`、operator 覆盖缺失、不同 reference 输出均是 harness 失败而非 not_met。
- operator 观察范围仅 Python token-row method boundary，不能扩展为 CUDA kernel 等价证明；其文件缺失或覆盖集合不同应 fail closed。
- 模板、stage、runner、输入和 review 任何一个 SHA 漂移都应停止关闭，不得以重新生成文件替代原证据。
- R023 的既有 not_met 不能被 R033 的诊断性或局部结果静默撤销；若 R033 的设计要改变其权威关系，需要独立的治理决议。
