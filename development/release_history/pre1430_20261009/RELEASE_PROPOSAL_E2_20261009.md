# E2 发布方案（13:40 OPSv2 更新，部署与推送仍未批准）

候选发布门已闭合；`release/e2` 与 `/data2/FreeToken/wt/release-e2` 已于 2026-10-09 13:03:20 创建，指向 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`。创建前复验 ref/目录不存在，创建后 tracked-clean，旧回滚树未变。[创建回执](RELEASE_E2_BRANCH_CREATION_20261009_v1.json)绑定这一事实。**部署、推送均未批准，未启动生产服务；生产配置的冷跑基准尚未产生。** 本方案提交用户审阅，批准后才能执行下列启动/回滚/冒烟操作。

依据：[13:00 指令](../plan/RELEASE_DIRECTIVE_20261009_1300.md)。完整起停与分时步骤见[统一操作手册](DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)，[发布说明](RELEASE_NOTES_E2_DRAFT_20261006.md)只陈述已验范围。旧方案、回滚手册和说明已原字节归档至 `release_history/*_pre1300_20261009.md`，不再把历史待批状态混入当前操作段。

| 项目 | 本次准备与证据 |
| --- | --- |
| 身份 | release/e2=481d3a7；保留 rollback `/data2/FreeToken/src/FreeToken`=184c965。工装 effb996、E3 8f6a912、D20 修复均不自动合入。 |
| 托管 | `setsid -f` 启动专用 supervisor；代码强制独立 session/group，处理 TERM/INT/HUP。服务也有独立进程组，使用冻结 D07 生命周期清理。 |
| 日志与 PID | 每次新建 `/data2/FreeToken/runs/production/<审批号>/`；`serve.log`、`owner.json`、`stopped.json`；supervisor 输出 `<审批号>.supervisor.log`；活动 PID/出生/PGID/session 文件 `/data2/FreeToken/run/production.active.json`。 |
| Restart/停止 | 外层 `Restart=no`；内部已验 OOM worker 恢复保持开启。TERM 120 秒，KILL 30 秒，操作命令总等候 220 秒；失败保留证据、写 quarantine 并阻断重启；finally 仅清理本次自有 lock/active，foreign lock 不碰，不启动回滚。 |
| 环境 | `os.environ.copy()` 后剔除所有 `FT_*`、`PYTHONPATH`、`CUDA_VISIBLE_DEVICES`，重设 FT venv、对应源码路径、GPU0、MASTER_PORT8096、unbuffered/禁写pyc；保留必要 CUDA/动态库及宿主环境。发布和回滚使用同一函数，不使用空环境。 |
| 发布配置 | 内网 `172.16.108.9:8095`，TCPStore8096；taskset1,3-47，offload NVFP4 Triton，PLE pinned，98304/.88，running/graph2，层优先4096，special-token checkpoint，mamba host slots0。 |
| GPU 分时 | supervisor 原子取得 `/data2/_shared/gpu.lock`，token含production owner/审批号/PID出生；E3共用锁存在即排队，禁8095/8096。生产常驻，测试须停服审批→停止→测试→恢复→冒烟，每次停服记录独立审批号。 |
| 鉴权选择 | 按二选一要求选择内网地址绑定，未添加 key 或修改 iptables；不绑定0.0.0.0。内网地址并不提供用户级鉴权。 |
| 冒烟 | 维护独占时段，官方 SDK 采集沿用 R066；执行由 `run_smoke.py` 编排：health、512提示/128输出、8257提示/128输出；绑定活动记录、活PID、实际argv、日志，首轮日志无prefill；每次new/cached行数与token总量精确核对，cached缺失不填0。保存SSE、usage、正文SHA和冷日志窗口。 |
| 回滚 | 完整停止命令等待GPU计算进程/8095/8096/锁/PID记录全部释放，再启动184c965；普通8192、窗口49152，使用同样环境清理/内网绑定/托管。量化触发见手册。 |

CPU准备包已上传并在 FT venv 验证：**39 passed，0 skipped**（CPU 行为验证；真实冒烟未执行）；本地同样通过。最终服务器档案为 `/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/`，源码清单、CPU输出与[回执](/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/evidence/receipt.json)均存档。`release_control.py --plan` 在服务器生成 Linux 最终argv，再与封存R056 `production/SERVE_CMD.txt`做diff；[发布diff](/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/evidence/release_vs_R056.diff)、[回滚diff](/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/evidence/rollback_vs_R056.diff)本地同字节保留。R056原命令SHA为 `e1708f7242325ca252fdd0d40219351473a2b49712f7ff1a63b3d78af7b54acb`，已核对原MANIFEST。

发布相对R056保持窗口/比例/running/graph/分块/量化/调度参数；差异是源码从0aa树移至481发布树、移除R056观测wrapper及其变量、使用ft生产入口、内网host和8095端口、加入专用托管。归档 v1 是早期 CPU 草案（Windows 本地 argv 带反斜杠，废弃）；v2 为修正 Linux argv 的中间包；v3 是历史归档；仅服务器 v4 source 中的 OPSv2 是当前操作包。历史包保留，不覆盖。

## 冒烟与失败即回滚

首次部署先限制业务方访问，待启动/健康维护状态为serving后执行两条冷请求。生产running/graph2的 `cold_baseline.json` 是首次现场基准，现阶段没有填写SHA或usage实测值；不得以R066历史graph4 SHA替代。恢复同一发布配置时逐项比较首次冷SHA和usage；回滚模式独立基准，不跨版本比较正文。任何HTTP/SDK/finish/usage/非法字符/缓存证据/身份或配置检查失败，都停止放量，按已批准手册回滚；原失败文件保留。它验证明确的两条接口契约，不代替业务任务合规。

## 已知限制与默认值

- T17逐位证据覆盖已测现算尾段≥65；≤64（含1）与同结构冷参照的GPU正确性仍待证。D20 CPU调度修复在独立开发树，未合入481，不改变发布范围。
- 并发或前缀命中时，temperature0正文不保证与独立冷请求相同。冷可复现、同结构热冷、并发无串号分别记录；R066c分类c的五条回复均有字面文法异常，不能声称普遍任务合规。
- 双会话已测最低剩余约378MiB（R058场景采样377.7MiB），由OOM恢复兜底；该数不是任意业务下的连续最低保证。R056 87K单请求约0.357GiB样本另列，不能混用。
- OOM故障注入只在chat路由做过一次（R061f），其余公开路由测试不能当成分别做过故障注入。R061f绑定481，现场发布树和候选树默认均为队列上限128、ready等待900秒；R061f结果显式timeout900，实际观测排队1。此为默认值一致，不是128并发压测。[默认值回读](/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/evidence/oom_defaults_readback.json)。
- 98304窗口上限仍拒绝越界；R056完整87100提示已测。32K解码中位34.33tok/s，对历史73728窗口38.30下降约10.4%，只作跨窗口披露。
- 旧not_met/failed_harness及原FTD03/04/erratum保留。FTD-20261009-1和论文v5/v5.1交付不构成部署批准。

## OPSv2 生命周期、H1 和 H2

服务器封存 OPSv2 位于 `/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/source`；CPU39 passed/0 skipped覆盖 H1、M1–M4、LOW、H3。正、反 rollback 冒烟均独立导出 `RELEASE_SMOKE_BASE`、`MODE`、`RUN_DIR`、`SERVE_LOG`、`OWNER`、`EXCLUSIVE_APPROVAL` 六变量，`run_smoke.py` 以 JUnit 要求1 passed/0 skipped。资源释放最多60秒，停止全程220秒；signal先于lock，finally仅清own lock/active，失败quarantine阻断新启动。外来prefill为smoke_invalid/exit75，同版重启重测不回滚；monitor每60秒，连续3失败或supervisor退出告警。

H2 当前阻断 rollback：HEAD/argv/68条Prefill正则已核，但 ignored status before/after非空；不自动清理或启动。历史日志缺API usage三字段，不能支撑R066 SDK usage。

## D20 与 GPU 队列

R067 按4格 `P8192/P8256 × T1/T64`、每轮最多10服务/14调用范围执行；b132因扩展缺失0调用失败，接入既有构建资产后b133首seed因旧T17 wrapper不兼容481异步API返回500。两轮均failed_harness（累计2服务/1请求尝试、0有效生成），无产品not_met；当前不改代码约束下停止。两轮D04封存，GPU/自有锁释放；≤64待证及论文C3保留。详见[R067实测报告](../plan/01_测试与调研/results/T20-E2-R067_20261009.md)。

R045 的旧 v18 已在 reserve 前被 R040g canonical `failed_harness` 阻断，实际0服务/0调用、无批次/锁/GPU，原件停止保留。替代计划是 `481` 的 AIPerf CPU 包：提案为 2 个串行服务、每服务2条并发 generation、合计4调用；部署后仍需新的 admission，当前不执行 GPU。Strata 22服务/345调用仍未批准。

发布门绑定见[E2闭合记录](E2_RELEASE_GATE_CLOSURE_20261009_v2.json)、[候选链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)、[R066c报告](../plan/01_测试与调研/results/T20-E2-R066c_20261009.md)。
