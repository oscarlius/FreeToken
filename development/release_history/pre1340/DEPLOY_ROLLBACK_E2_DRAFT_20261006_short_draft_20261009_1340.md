# E2 部署与回滚操作草案（待批准）

只可在实际部署/停服/回滚批准后执行。当前不得启动模型、GPU 或生产 endpoint。操作源码仅用 `/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/source` 中封存的 OPSv2，并先核对 source manifest、argv 与环境 diff。

启动前必须：目标 HEAD 和 `git status --porcelain --untracked-files=all --ignored` 均干净；无 active/quarantine、GPU/8095/8096/共享锁冲突；使用新 run_dir 和真实审批号。H2 目前失败：rollback HEAD 正确但 ignored 状态非空，保持阻断，不自动清理。

`release_control.py --plan` 是惰性输出。实际启动由 setsid supervisor 处理；信号先于锁，服务/monitor cwd 均是 run_dir。资源释放最多 60 秒；停止总上限 220 秒；finally 仅清 own child、lock、未替换 active。清理异常写 quarantine，禁止新启动。monitor 每 60 秒 health；连续 3 失败或 supervisor 退出告警。

H1 正反冒烟必须完整导出：

```bash
export RELEASE_SMOKE_BASE=http://172.16.108.9:8095
export RELEASE_SMOKE_MODE=release_or_rollback
export RELEASE_SMOKE_RUN_DIR=/data2/FreeToken/runs/production/APPROVAL/smoke_first
export RELEASE_SMOKE_SERVE_LOG=/data2/FreeToken/runs/production/APPROVAL/serve.log
export RELEASE_SMOKE_OWNER=/data2/FreeToken/run/production.active.json
export RELEASE_SMOKE_EXCLUSIVE_APPROVAL=ACTUAL_APPROVAL_ID
```

`run_smoke.py` 的 JUnit 门为 1 passed / 0 skipped。外来 Prefill 写 `smoke_invalid` 并 exit 75；同版重启重做冷冒烟，不自动回滚。rollback 参数是普通 8192 / 49,152；需要新的停服/回滚审批。H1/H2/H3、身份、SDK、usage、缓存或文本检查失败均停止放量并保留原件。
