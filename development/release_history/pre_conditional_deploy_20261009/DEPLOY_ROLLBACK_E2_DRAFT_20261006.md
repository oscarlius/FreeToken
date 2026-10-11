# E2 部署与回滚手册（14:30 OPSv5 当前方案）

**分支已创建；生产部署和推送未批准、未执行。** 本文件中的启动、停止和真实冒烟命令都是审批后的操作步骤。代码已完成CPU准备与服务器归档，尚无生产PID或首次冷跑SHA。候选481、回滚184c965、最终argv/R056差异和证据见[发布提案](RELEASE_PROPOSAL_E2_20261009.md)。

## 托管与环境

最终操作源码在 `/data2/FreeToken/runs/dev_release/release_e2_ops_v5_20261009_review/source/development/release_e2_ops_v2`，源码和 `binary_manifest.json` 均由该归档的 `evidence/receipt.json` 绑定。运行前核对该清单。`release_control.py --plan --mode release|rollback`只打印完整 `ft serve` argv 与环境投影，不启动任何东西；审批前以该输出、源码哈希、binary manifest 与封存 full-argv/R056 diff 逐项核对。

采用 `setsid -f` 创建独立supervisor，无外层自动重启（Restart=no）。supervisor PID/出生/PGID/session及服务组写入 `/data2/FreeToken/run/production.active.json`，每次目录的 `owner.json`保留相同记录；服务日志 `serve.log`，外层日志 `<审批号>.supervisor.log`。处理TERM/INT/HUP并按owned group清理；信号处理器先于锁登记；TERM120秒、KILL30秒、控制命令总等待220秒。进程身份变更、锁替换、GPU/端口未释放时fail closed，保留诊断，不使用killall或抢删锁。

发布/回滚均调用 `release_config.environment()`：复制宿主环境，删除所有FT_*及旧PYTHONPATH/CUDA_VISIBLE_DEVICES，再设对应树python目录、FT venv、GPU0、MASTER_PORT8096、PATH、PYTHONUNBUFFERED、PYTHONDONTWRITEBYTECODE。启动前 `validate_worktree` 精确验证对应 path/HEAD/commit 与 `binary_manifest.json`：仅 `__pycache__`、`.pytest_cache`、`*.egg-info` 可作为普通缓存项；扩展只允许 manifest 中精确相对路径和 SHA 匹配的普通实体 `.so`。其他 ignored/untracked、任何 tracked 变动、路径逃逸和符号链接都拒绝，且不删除缓存。

## 发布启动（批准后）

每次使用实际审批号替换占位符，生产目录与日志必须从未存在。先确认发布源码/门hash、内网IP、GPU闲、共享锁不存在、8095/8096无监听，并限制业务方访问直到冒烟完成。

```bash
OPS=/data2/FreeToken/runs/dev_release/release_e2_ops_v5_20261009_review/source/development/release_e2_ops_v2
DEPLOY_APPROVAL=REPLACE_WITH_ACTUAL_DEPLOYMENT_APPROVAL_ID
[[ "$DEPLOY_APPROVAL" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$ ]] || exit 2
mkdir -p /data2/FreeToken/runs/production /data2/FreeToken/run
( set -C
  setsid -f /data2/FreeToken/venv/bin/python "$OPS/release_control.py" \
    --start --mode release --approval-id "$DEPLOY_APPROVAL" \
    --run-dir "/data2/FreeToken/runs/production/$DEPLOY_APPROVAL" \
    </dev/null >"/data2/FreeToken/runs/production/$DEPLOY_APPROVAL.supervisor.log" 2>&1
)
```

`setsid`返回不等于服务就绪。回读active/owner的实际PID出生和argv；用 `/health`确认status=ok且maintenance=serving。冷启动允许最多1800秒，每10秒检查一次；超时停止放量并触发回滚。首个模型请求必须来自下面的冒烟测试，维护独占窗口内禁止其他业务请求；无法证明独占则不签冷基准。首次冷基准验证的是当前running/graph2配置。

```bash
export RELEASE_SMOKE_BASE=http://172.16.108.9:8095
export RELEASE_SMOKE_MODE=release
export RELEASE_SMOKE_OWNER=/data2/FreeToken/run/production.active.json
export RELEASE_SMOKE_SERVE_LOG="/data2/FreeToken/runs/production/$DEPLOY_APPROVAL/serve.log"
export RELEASE_SMOKE_RUN_DIR="/data2/FreeToken/runs/production/$DEPLOY_APPROVAL/smoke_first"
export RELEASE_SMOKE_EXCLUSIVE_APPROVAL="$DEPLOY_APPROVAL"
unset RELEASE_SMOKE_BASELINE
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  "$OPS/run_smoke.py"
```

测试只调用现有服务，不启动模型；使用R066官方SDK输入512/8257、各128输出、temperature0，SDK禁重试，单请求timeout900秒。绑定active文件、活服务PID出生、准确host/argv/commit/log；要求此前无prefill、每条日志new/cached总量和分块行数匹配。API cached字段缺失按缺失记录，以backend日志证明冷；没有日志证据则失败。**唯一例外是外来 Prefill：`run_smoke.py` 写 `smoke_invalid.json` 并以 exit75 退出，先停止本轮，保持同一候选重启后重测；它不触发跨候选回滚。**保存health、原SSE/usage、正文SHA、日志字节窗口和 `cold_baseline.json`。这两条互相无公共token前缀；维护独占是必要条件，现有backend日志没有逐request ID，不声称其本身提供直接UID绑定。

首次cold SHA是现场记录，没有借用graph4旧值。后续恢复发布服务设 `RELEASE_SMOKE_BASELINE=<首次smoke_first/cold_baseline.json>`逐项比较相同模式/窗口/分块下SHA和usage。业务放量仅在完整冒烟通过后。

## 完整停止与回滚（批准后）

以下停服必须用真实停服/回滚审批号，不能拿任意自填字符串当批准。stop命令先绑定supervisor出生，再写 `stop_<审批号>.json`，触发owned清理，等待GPU计算进程、8095/8096、共享锁、active记录全部释放。

```bash
STOP_APPROVAL=REPLACE_WITH_ACTUAL_DOWNTIME_APPROVAL_ID
[[ "$STOP_APPROVAL" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$ ]] || exit 2
/data2/FreeToken/venv/bin/python "$OPS/release_control.py" \
  --stop --approval-id "$STOP_APPROVAL"
ss -H -ltn '( sport = :8095 or sport = :8096 )'
nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits
test ! -e /data2/_shared/gpu.lock
test ! -e /data2/FreeToken/run/production.active.json
test ! -e /data2/FreeToken/run/production.cleanup_failed.json
```

stop退出必须为0，ss与compute输出为空，lock、active和cleanup_failed都不存在；GPU显存回落到启动idle门槛（各卡<1000MiB），才可进入回滚。任一失败保留证据并写入 quarantine、阻断重启；finally 仅清理本次 own lock/active，foreign lock 一律不碰，不能继续启动旧服务。新的审批号启动旧版；不切换、不覆盖新树：

```bash
ROLLBACK_APPROVAL=REPLACE_WITH_ACTUAL_ROLLBACK_APPROVAL_ID
[[ "$ROLLBACK_APPROVAL" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$ ]] || exit 2
( set -C
  setsid -f /data2/FreeToken/venv/bin/python "$OPS/release_control.py" \
    --start --mode rollback --approval-id "$ROLLBACK_APPROVAL" \
    --run-dir "/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL" \
    </dev/null >"/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL.supervisor.log" 2>&1
)
export RELEASE_SMOKE_MODE=rollback
export RELEASE_SMOKE_BASE=http://172.16.108.9:8095
export RELEASE_SMOKE_OWNER=/data2/FreeToken/run/production.active.json
export RELEASE_SMOKE_SERVE_LOG="/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL/serve.log"
export RELEASE_SMOKE_RUN_DIR="/data2/FreeToken/runs/production/$ROLLBACK_APPROVAL/smoke_first"
export RELEASE_SMOKE_EXCLUSIVE_APPROVAL="$ROLLBACK_APPROVAL"
unset RELEASE_SMOKE_BASELINE
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  "$OPS/run_smoke.py"
```

回滚同样先等health=serving并独占冒烟；上面的 rollback 块已独立导出六个 `RELEASE_SMOKE_*` 变量，不能沿用 release 值。回滚的SHA只形成其自己的基准，不与发布SHA跨版本比较。失败保留日志并停止，不自行切第三个候选。

**回滚窗口选49152。** 对应旧184c965的历史普通8192配置，`/data2/_shared/runs/ft_rounds/_e0/paper_headroom_20261003/serve_final_8192.log`的解析参数及[8192复核](../RESULTS_FT_PAPER_HEADROOM_20261003.md)、[历史32K记录](../RESULTS_FT_COLD32K_20261002.md)支持49152。32768只见于历史启动脚本，不是该已核实回滚配置；不沿用候选98304，不开层优先。旧版含K1，回滚降低的是新版本风险，不声称旧版无缺陷。旧E0归档不是当前D04规范下独立封存轮次。

| 量化触发 | 处理 |
| --- | --- |
| 初启1800秒仍未serving，或任一冒烟请求900秒未完成 | 不放量，保存日志并回滚。 |
| 任一冒烟HTTP/SDK/finish/usage/非法字符/缓存证据/身份配置失败；同配置恢复SHA或usage不符 | 一次即触发；保存失败产物，回滚。 |
| OOM后900秒未恢复serving，或重启进入terminal/dead状态一次 | 回滚。 |
| 10分钟内≥2次OOM/worker restart | 回滚；单次成功恢复保留记录，不单凭低显存样本回滚。 |
| serving期间连续3次health失败（monitor间隔60秒），或5分钟内≥3次非预期5xx/worker错误 | 停止新流量，回滚。显式输入超窗/客户端取消不计服务故障。 |
| 已确认串号、非法控制字符或错误usage一次 | 停止新流量，保留原输出并回滚。一般业务答案质量另按业务验收，不声称脚本可自动判真。 |

这些是待批准的运维阈值，不是本次CPU检查测得的故障率。上表的“缓存证据失败”不覆盖外来 Prefill：该情形优先按前述 `smoke_invalid.json`/exit75 同版重测处置。部署批准应包含上述失败分支的停止/回滚授权；当前没有这项授权，未执行任何命令。

## 生产常驻与按需测试

启动时production owner登记共享GPU锁，E3入口锁存在即排队、保留端口8095/8096全部禁用（R045 v18实测FILEdry端口另用）。每次测试流程为：记录本次停服审批号 → 上述stop并验证全部释放 → 独立测试批次取得同一锁 → 测试终态与owned清理 → 新恢复审批号用release模式启动 → 与首次graph2冷基准比较的独占冒烟 → 放量。审批号同时出现在停服JSON、owner、run目录及协调记录，不能靠后台kill绕过审批。生产部署批准到达时，E3在当前批次边界让出，不抢杀进行中服务。

## H2 工作树准入已通过

回滚树 `184c965…` 的 HEAD、完整 argv 加 `--help` 和白名单 before/after 均已只读核实；`.pytest_cache`、egg-info 与 `__pycache__` 被逐项接受，rollback 两个既有实体扩展由 manifest 路径/SHA 绑定。未自动清理或绕过检查。完整回执在 `release_e2_ops_v2/h2_allowlist_evidence_v2/h2_receipt.json`。`stream_completion_chunks` 的 `include_usage` gate 保留；68 条历史 Prefill 正则不能替代 HTTP/API usage。

## CPU验证与未执行项

服务器最终 OPSv5 包为48 passed、0 skipped；覆盖 H1、M1–M4、LOW、H3、工作树白名单、环境不污染、两个argv、PID出生拒绝、资源释放≤60秒、TERM/INT/HUP、quarantine、发布/回滚冒烟owner/地址/审批绑定和JUnit 1 passed/0 skipped 门。M2 外来 Prefill 触发 `smoke_invalid.json`/exit75，只能在同版重启后重测，不回滚到其他候选。M1 health 明确要求 `status=ok` 且 `maintenance=serving`；M3 监控产物为运行目录内 `health_monitor.jsonl`、`alerts.jsonl` 与 `monitor.log`。没有启动模型服务或做真实OOM/停服恢复演练；这部分只能在批准后留现场证据。服务器最终argv和R056 diff已经生成，不以CPU通过代替生产验收。

R067b/batch134 的 GPU 工装终态不改变本手册的部署准入：实际 1 service 在 load 阶段因 artifact copy loop 覆盖 service name 而由已验证 PID birth 的 TERM 收束，0 generation、0 cell，failed_harness。累计 R067 为3 service/1 request attempt/0 valid；cleanup_errors[]、GPU4MiB、compute PID空与锁释放已封存。完整重跑尚需10 additional、超过原后缀cap，等待用户新 round 裁定；不得以此 CPU 修复或 H2/CPU48 证据启动服务。
