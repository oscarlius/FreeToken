# restore09 CPU 就绪报告（晚间窗口指令 E0-4：停止与恢复 481）

构建时间：2026-10-11 10:50 前后（E0，纯 CPU，未执行任何停止/启动）。目录：`/data2/FreeToken/development/kimi_phase2_20261011/restore09/`（本地同名镜像）。来源包 restore08 未改动。

## 0. 关键分工：停止用 restore08，恢复用 restore09

晚间窗口停的是**当前正在运行的生产 -08**：`stop_approved_restore.py` 内置"拒绝停止外来 owner"检查（`production.active.json` 的 approval_id 必须等于本包审批号），因此停止命令必须用 **restore08 包**（审批 -08，指令 E1 的命令正是它）。restore09（审批 -09）只承担窗口最后一步的**恢复**（启动 + SDK 冒烟 + df77cb 对比 + 失败回滚）。

## 1. 停止命令（E1；现在不执行）

```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```

成功判据（指令 E1）：退出码 0；`runs/production/RESTORE481-MORNING-20261011-08/stopped.json` 存在；`production.active.json` 已移除；`gpu.lock` 已释放；`nvidia-smi` 无计算进程。

前置（按补充指令 A1/A2）：E0-5 已写协调日志；-08 观察器已按 A2 提前结束并写 `evening/OBSERVER_EARLY_STOP.json`；无 STOP 文件；env 检查为 0。

## 2. 恢复命令（E5；restore09，分三步，不用 deploy_conditional.py --execute）

```bash
# 1) 启动（内含全部 preflight：工作树/原生扩展清单、GPU 空闲、8095/8096 无监听、无锁、run_dir 不存在）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore09 && \
  /data2/FreeToken/venv/bin/python start_approved_release.py'

# 2) 等待 serving 并执行 SDK 冒烟（df77cb 基准 15 字段与启动参数逐项对比）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore09 && \
  CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py'

# 3) 冒烟通过后启动任务观察器（后台脱离，--until 2026-10-12T09:00:00+08:00）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore09 && \
  setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py \
  > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-09/observer_outer.log 2>&1'
```

## 3. 回滚命令（启动或冒烟失败时）

```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore09 && \
  /data2/FreeToken/venv/bin/python -c "import subprocess; from deploy_conditional import recover_after_restore_failure; raise SystemExit(recover_after_restore_failure(subprocess.run))"'
```

行为与 restore08 相同：记失败回执 → 停 -09 → 起 ROLLBACK184-MORNING-20261011-09 → 回滚冒烟。任一步非 0 即失败：不重试；回滚也失败则写 `PRODUCTION_DOWN.md` 并在协调日志标"紧急"。

## 4. 与 restore08 的 diff（`kimi_phase2_20261011/diff_restore09.txt` 全文）

6 个文件有差异，全部是 E0-4 允许的身份/派生项：

| 文件 | 改动 |
|---|---|
| DEPLOYMENT_APPROVAL.json | approval_id/rollback_approval/run_dir/scope×2：-08→-09；observation_until→2026-10-12T09:00:00+08:00；package_source_manifest_sha256 同步新清单（门链派生）。recorded_at 保持 restore08 原值（E0-4 验收未列入可改项，签署时间以协调日志为准） |
| observe_overnight.py | 第 37 行审批号 -08→-09（LF） |
| test_cpu_orchestration.py | 4 处身份串 -08→-09（LF） |
| SOURCE_MANIFEST.json | 上述两 .py 的新 SHA；package 字段 restore08→restore09 |
| ROOT_FINAL_REVIEW.json | approval_id -09；approval_sha256=`8c0c2365…672106`；independent_review_sha256=晚间主指令 SHA `dd89778a…e7decb`（服务器与本地副本已核对一致）；pending_independent_review=false（restore08 已带此值，diff 中不显）；package_source_manifest_sha256 同步；scope 内身份名替换 |
| README.md | 身份说明重写为 restore09/晚间窗口（单行） |

**已知差异说明**：`Only in restore08: EXECUTION_TIME_PREFLIGHT.json`——这是今晨 09:19 恢复执行时工装自身写出的执行回执（证据），不是包源码，未复制进 restore09，原样保留在 restore08 中。ROOT_FINAL_REVIEW 的 scope 文本沿用了 "stage-1 copy" 措辞（实际为 E0 构建），以本文件与 README 为准。

其余 10 个源文件逐字节相同。df77cb 基准（first_cold_baseline SHA `df77cb14…f9d97`）与冻结 ops 路径原样保留。

## 5. CPU 测试输出（CUDA 关）

- 本地：`python -B -m pytest test_cpu_orchestration.py -q` → **7 passed**；门链 `GATE_CHAIN_PASS RESTORE481-MORNING-20261011-09 2026-10-12T09:00:00+08:00`。
- 服务器：同命令 → **7 passed in 0.02s**；门链同上。
- 全部文件已 `chmod 0444` 封存（目录保持可写以便运行时写回执）。

## 6. 新 SHA256（两侧一致）

- DEPLOYMENT_APPROVAL.json：`8c0c236545b2077658fbea7e91558c0b17012b1ca29a917e459de48fb4672106`
- ROOT_FINAL_REVIEW.json：`e955088b851ca81f005bfb12a2e94fccb341be0f489528c33abd3bc92f62067c`
- SOURCE_MANIFEST.json：`d0ac315a64b3428d43bf974aafbdfd379eb21933c175b0a698627ee976305104`
- observe_overnight.py：`b68e69ab87995b2bbd07e8bd2df3b5b90fd26ef8e7a2bdd3e6c87631adcdec6c`
- test_cpu_orchestration.py：`90f103443ca0471df7821c0166e9218b5eb6d24bb50b8535af20c58a45a7a254`
