# P1 非零解码快照准备

这是 P1 的只读准备工具，不是 P1 执行、GPU 证明或验收。P0/T17 仍是当前优先级；只有未来已接受的 `E2-base.1` 与该提交上的默认 T16 `kept` 收据，才可将真实工件交给此工具检查。

## 已核对的历史边界

T03 的真实封存轮是服务器 `/data2/_shared/runs/ft_rounds/E2-R008`，batch 29，基线
`E2-base@23f2e2c`。本次只读读取六个 `snapshot_count.json`，A/B 三个独立进程均为：

```json
{"actual_successful_snapshots": 0}
```

因此 E2-R008 只能作为“零覆盖缺口”的证据，不能作为未来 P1 的正例。它的结果文档也明确写明
“不能证明非零成功快照路径已覆盖”。

T03 的原始三进程结构是 `p1/p2/p3`，每个进程包含 A、B 两臂；新 P1 准备校验器要求**三条独立
正例链**，并非把 T03 的六个零计数臂转换成正例。

D01/T03 的当前可观察事实有严格界限：

- `plan/01_测试与调研/batches/t03_runner.py:190-193` 只从服务日志唯一的
  `D0 anchor_snapshots_taken=N` 终行读取成功副本计数。
- `development/e2base/python/freetoken/scheduler/cache.py:229-253` 在真实 decode 锚点调用
  `pool.copy_from(live_slot, ping_pong_slot)` 后才递增该计数。
- `development/e2base/python/freetoken/scheduler/scheduler.py:658-676` 的命中恢复把
  `mamba_restore_src` 复制到新 live slot；旧 T03 的 final count 并不记录 donor/consumer UID 或 slot。

所以仅有非零计数也不够：P1 的真实运行必须额外保留 decode、donation 与 restore 的 UID/slot/device-token
绑定。该要求是工装协议，不要求也不改变 engine。

## 准备校验器

`p1_snapshot_prepare.py --evidence <retained-evidence.json>` 只读打印一个验证摘要，绝不写轮次。
它只检查传入 JSON 中声明字段的 schema、SHA 字符串格式和字段间关系；**不会**打开或核验原始
response/log/receipt 文件的 SHA 或内容，不会核验 accepted-baseline/T16 收据内容，也不会证明服务
进程曾真实出生。因此通过结果不是 GPU 运行、真实正例或 P1 接受证据。
输入协议 `p1_snapshot_evidence/v1` 必须包含：

- 已接受 `E2-base.1@<short>` 的完整 40 位提交和接受收据 SHA；同提交的默认 T16 `kept` 收据。
- 原始 tokenized 输入的 int32le SHA、原始 trace SHA、tokenizer 源 SHA 和 token 数。
- 恰好三个唯一 process 记录；每条记录必须绑定同一 commit、serve/startup/runner/compiled-extension SHA 与 tokenizer SHA。
- 每条记录的实际 decode 成功计数必须为正，并将 decode `{uid, slot, device_tokens}` 原样绑定到 donation。
- restore 必须引用 donation slot 和相同 device token 数，目标 slot 不得别名 donor slot，consumer UID 必须不同。
- consumer admission 的 UID 必须等于 restore UID，`cached_tokens` 必须等于 donated
  `device_tokens`，且 prompt 必须有真实的后续 token。
- consumer 的完成状态、正 completion token 数、原始响应 SHA 与 donor-prefix 的 tokenized-input SHA 必须同时存在。

任何零计数、缺少第三进程、跨提交、UID/slot/token 长度不绑定、consumer 没有成功完成，都会拒绝。通过只表示
工件结构和绑定完整；它不能替代保留的服务日志、原始响应、实际启动收据或独立复核，也不宣布 P1 接受。

## 未来运行协议

未来运行须以原 T03 的三独立进程原则保留原始服务目录和 exact source/input bindings。每个正例要先完成
真实 decode 锚点副本，再由真实 radix donation 产生前缀，最后由不同 UID 的命中请求恢复到不同 live slot 并完成。
禁止用手写 JSON、单元测试、计数模拟或任意“consumer”替代 GPU 路径。若需要新增 runtime 观测字段或修改
P1 的三进程设计，先向负责人报告；本准备工具不扩大范围。

## CPU 验证

```powershell
python -m pytest -q -p no:cacheprovider development/tests/test_p1_snapshot_prepare.py
```

测试只覆盖协议拒绝逻辑：正例形状、零计数、三进程数、donation/restore UID-slot、token 输入、commit 与 T16
接收条件；没有 GPU、服务或轮次写入。
