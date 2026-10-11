# R061 实际 OOM 故障注入工装交接

候选固定为 `608251f00deea85a0b12b31cc1f43725f45fbf9b`，父提交为
`0aa23431e5b800797543bdecbf35a01045131d7d`，只可在
`/data2/FreeToken/wt/e2oom-recovery` 执行。该工装不修改候选产品树。

`r061_oom_fault_prepare_v1.py` 的正式路径只接受产品 scheduler 的
`FT_DEV_OOM_INJECT=1`、UID=1、`before_forward` 和产品 receipt；没有外部
Engine hook、没有 DEV ACK。它要求同结构 128/temp=0 普通冷参照、UID1 注入、
重启中 UID2 排队、重启后 UID2 完成。冷参照与恢复输出都由原始 SSE +
UserMsg/Detokenize 物理 token sidecar 绑定。受影响请求只有原始 API error
文档才算错误，Python exception 文本不算证据。

正式结果必须同时包含：

- API PID/start ticks 在故障前后相同；`/health` 在故障窗口记录
  `maintenance=restarting`、`restart_waiters>=1`，并在新 epoch 回到 serving。
- receipt 的 UID=1、count=1、point=before_forward、PID、时间和 epoch；
  对照、故障、排队的输入 SHA 和 UID/epoch 绑定。
- 故障前 worker 的完整 birth 集合均已退出（PID 复用时 start ticks 必须不同）；
  每个 observer snapshot 在结果中以 `epoch-<n>` 目录留存，避免新 worker 覆盖旧文件。
- 参照与排队完成的物理 token 序列 SHA 和完整 SSE 文本 SHA 都相同。

## R061 实际 FILEDRY（R 执行前置）

在没有 GPU 锁、服务、请求、batch 的 CPU-only 时段，用正式脚本、正式 cwd 和
正式 UID 执行。`REFERENCE_JSON`、`AFFECTED_JSON`、`QUEUED_JSON` 必须是 R061
审过的三份常规 SSE payload；它们不能是临时重写文件。以下命令中的运行目录必须
从未存在：

```bash
export CUDA_VISIBLE_DEVICES=''
export PYTHONPATH=/runs/dev_R046/r046b_section12_source_v4/cpu_guard${PYTHONPATH:+:$PYTHONPATH}
cd /data2/FreeToken/wt/e2oom-recovery
/data2/FreeToken/venv/bin/python -c 'import sitecustomize; print("R061_CPU_GUARD_ACTIVE")'
/data2/FreeToken/venv/bin/python /data2/FreeToken/wt/e2oom-recovery/development/r061_oom_fault_prepare_v1.py \
  --file-dry-run /data2/FreeToken/runs/dev_OOM/r061_608251_filedry_YYYYMMDD_HHMM \
  --candidate-commit 608251f00deea85a0b12b31cc1f43725f45fbf9b \
  --worktree /data2/FreeToken/wt/e2oom-recovery \
  --reference-input "$REFERENCE_JSON" --affected-input "$AFFECTED_JSON" --queued-input "$QUEUED_JSON"
sha256sum /data2/FreeToken/runs/dev_OOM/r061_608251_filedry_YYYYMMDD_HHMM/receipt.json
stat -c '%a %n' /data2/FreeToken/runs/dev_OOM/r061_608251_filedry_YYYYMMDD_HHMM/receipt.json
```

该空跑会使用正式 writer、复制全部运行源（每项 SHA-256 + MD5 + 0600）、写入
output probe、并探测相邻 API/TCPStore 端口，但不 listen/connect、不启动 Popen、
不创建 formal RID 目录、不取锁、不分配 batch。receipt 封存为 0444。R 审签必须将
FILEDRY receipt SHA、当前 source capsule SHA、candidate、native provenance 和
startup review 全部写入同一个只读 review/pin；不要以尚未签字的 FILEDRY 反向证明
其自身。

## 正式前置与入口

控制器在 reservation 前、child 在取锁前再次验证：candidate/worktree、R060 native
proof `/data2/FreeToken/runs/dev_OOM/r060_608251_native_provenance_20261007.json`
（SHA `0d09b38c508783c0dd9d9e743a6d9174e3f126667791e1d40cd53f5def1eeb3d`、0444）、
sealed FILEDRY receipt、sealed R startup review、候选的 recovery/control/scheduler
源码。随后由 root/R 在锁空闲时调用：

```bash
/data2/FreeToken/venv/bin/python /data2/FreeToken/wt/e2oom-recovery/development/r061_oom_fault_prepare_v1.py \
  --run --candidate-commit 608251f00deea85a0b12b31cc1f43725f45fbf9b \
  --worktree /data2/FreeToken/wt/e2oom-recovery \
  --reference-input "$REFERENCE_JSON" --affected-input "$AFFECTED_JSON" --queued-input "$QUEUED_JSON" \
  --file-dry-receipt "$SEALED_FILEDRY_RECEIPT" --startup-review "$SEALED_R061_STARTUP_REVIEW"
```

控制器只 reserve 并发布 child birth receipt；child 才在再次复核后取锁。若任一
health/queue/epoch/worker/API/error/SSE/token 证明不满足，结果必须 failed_harness，
不得将异常 repr、提交后的完成记录或 API 自比写成排队/恢复成功。

当前仅有 Linux CPU 67 PASS（`OOM_FINAL608251_ACTUAL_LINUX_CPU_20261007.json`），
它不是 R061 GPU 验收。R061 未执行 FILEDRY、未取锁、未启动服务、未发请求。
